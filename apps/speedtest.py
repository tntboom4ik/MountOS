"""
MountOS — Проверка скорости интернета.

Измеряет:
  • Задержку (ping) до серверов
  • Скорость загрузки (download)
  • Скорость отдачи (upload)
  • Потерю пакетов
  • IP-адрес и провайдер

Тесты реальные — через публичные endpoints:
  • Ping       — Cloudflare 1.1.1.1 или Google DNS
  • Download   — Cloudflare speed.cloudflare.com
  • Upload     — POST на speed.cloudflare.com
  • IP-адрес   — ip-api.com (бесплатный, без ключа)

Всё работает без сторонних библиотек, кроме urllib + socket.

Установка: apps/speedtest.py + перезапуск MountOS.
"""

import json
import time
import socket
import subprocess
import statistics
import urllib.request
import urllib.error
from datetime import datetime

from PySide6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QLabel,
                                QPushButton, QProgressBar, QFrame,
                                QSizePolicy, QScrollArea, QMessageBox)
from PySide6.QtCore import Qt, QTimer, QThread, Signal, QRectF, QPointF
from PySide6.QtGui import (QPainter, QColor, QPen, QBrush, QPainterPath,
                            QLinearGradient, QFont, QConicalGradient, QIcon)

from ui.icons import get_icon
from ui.settings_state import state

APP_NAME = "SpeedTest"
APP_ICON = "grid"
APP_VERSION = "1.0"
APP_AUTHOR = "MountOS"


# ============================================================
#  Поиск Desktop
# ============================================================

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
#  Хелперы
# ============================================================

def fmt_speed(mbps: float) -> str:
    """Форматирует скорость."""
    if mbps < 1:
        return f"{mbps * 1000:.0f} Кбит/с"
    return f"{mbps:.2f} Мбит/с"


def fmt_ms(ms: float) -> str:
    if ms < 1:
        return f"{ms * 1000:.0f} мкс"
    return f"{ms:.1f} мс"


def fmt_bytes(bps: float) -> str:
    units = ["Б/с", "КБ/с", "МБ/с", "ГБ/с"]
    f = float(bps)
    for u in units:
        if f < 1024:
            return f"{f:.1f} {u}"
        f /= 1024
    return f"{f:.1f} ТБ/с"


# ============================================================
#  Воркеры
# ============================================================

class PingWorker(QThread):
    result = Signal(float, float)   # avg_ms, packet_loss_percent
    error = Signal(str)

    def __init__(self, host: str = "1.1.1.1", count: int = 8):
        super().__init__()
        self.host = host
        self.count = count

    def run(self):
        try:
            results = []
            lost = 0
            is_windows = subprocess.os.name == "nt"

            for i in range(self.count):
                try:
                    if is_windows:
                        # Windows — ping через subprocess
                        out = subprocess.run(
                            ["ping", "-n", "1", "-w", "2000", self.host],
                            capture_output=True, text=True, timeout=3,
                            creationflags=subprocess.CREATE_NO_WINDOW
                            if hasattr(subprocess, "CREATE_NO_WINDOW") else 0)
                        if out.returncode != 0:
                            lost += 1
                            continue
                        # Ищем "time=XXms" или "время=XXмс"
                        import re
                        m = re.search(r"(?:time|время)[=<]([0-9]+)\s*ms",
                                      out.stdout, re.IGNORECASE)
                        if not m:
                            m = re.search(r"(?:time|время)[=<]([0-9]+)",
                                          out.stdout, re.IGNORECASE)
                        if m:
                            results.append(float(m.group(1)))
                        else:
                            lost += 1
                    else:
                        # Linux/Mac — ping через subprocess
                        out = subprocess.run(
                            ["ping", "-c", "1", "-W", "2", self.host],
                            capture_output=True, text=True, timeout=3)
                        if out.returncode != 0:
                            lost += 1
                            continue
                        import re
                        m = re.search(r"time=([0-9.]+)\s*ms", out.stdout)
                        if m:
                            results.append(float(m.group(1)))
                        else:
                            lost += 1
                except Exception:
                    lost += 1

            if not results:
                self.error.emit("Нет ответа от сервера")
                return

            avg = statistics.mean(results)
            loss_pct = lost / self.count * 100
            self.result.emit(avg, loss_pct)
        except Exception as e:
            self.error.emit(str(e))


class IpInfoWorker(QThread):
    result = Signal(dict)
    error = Signal(str)

    def run(self):
        try:
            url = "http://ip-api.com/json/?fields=status,country,countryCode,regionName,city,isp,org,as,query,timezone"
            req = urllib.request.Request(url, headers={"User-Agent": "MountOS/1.0"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            if data.get("status") == "success":
                self.result.emit(data)
            else:
                self.error.emit("Не удалось определить IP")
        except Exception as e:
            self.error.emit(str(e))


class DownloadWorker(QThread):
    """Тест скорости загрузки через Cloudflare."""
    progress = Signal(float)     # текущая скорость Мбит/с
    result = Signal(float)       # финальная средняя скорость
    error = Signal(str)

    def __init__(self, duration_sec: int = 10):
        super().__init__()
        self.duration_sec = duration_sec

    def run(self):
        try:
            url = ("https://speed.cloudflare.com/__down?bytes=25000000")
            # 25 МБ
            start = time.time()
            total_bytes = 0
            samples = []
            last_check = start
            last_bytes = 0

            req = urllib.request.Request(url,
                                          headers={"User-Agent": "MountOS/1.0"})
            with urllib.request.urlopen(req, timeout=self.duration_sec + 5) as resp:
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    total_bytes += len(chunk)
                    now = time.time()
                    elapsed = now - start
                    if now - last_check >= 0.3:
                        dt = now - last_check
                        speed_bps = (total_bytes - last_bytes) / dt
                        speed_mbps = speed_bps * 8 / 1_000_000
                        samples.append(speed_mbps)
                        self.progress.emit(speed_mbps)
                        last_check = now
                        last_bytes = total_bytes
                    if elapsed >= self.duration_sec:
                        break

            if not samples:
                self.error.emit("Не удалось измерить скорость")
                return

            # Средняя по последним 70% сэмплов (без старта)
            tail = samples[int(len(samples) * 0.3):] or samples
            avg = statistics.mean(tail)
            self.result.emit(avg)
        except Exception as e:
            self.error.emit(str(e))


class UploadWorker(QThread):
    """Тест скорости отдачи через Cloudflare."""
    progress = Signal(float)
    result = Signal(float)
    error = Signal(str)

    def __init__(self, duration_sec: int = 10):
        super().__init__()
        self.duration_sec = duration_sec

    def run(self):
        try:
            url = "https://speed.cloudflare.com/__up"
            # Отправляем POST по 1 МБ чанков
            chunk = b"x" * (512 * 1024)   # 512 КБ

            start = time.time()
            total_bytes = 0
            samples = []
            last_check = start
            last_bytes = 0

            while time.time() - start < self.duration_sec:
                req = urllib.request.Request(
                    url,
                    data=chunk,
                    method="POST",
                    headers={
                        "User-Agent": "MountOS/1.0",
                        "Content-Type": "application/octet-stream",
                    })
                try:
                    with urllib.request.urlopen(req, timeout=15) as resp:
                        resp.read()
                except Exception:
                    break

                total_bytes += len(chunk)
                now = time.time()
                if now - last_check >= 0.3:
                    dt = now - last_check
                    speed_bps = (total_bytes - last_bytes) / dt
                    speed_mbps = speed_bps * 8 / 1_000_000
                    samples.append(speed_mbps)
                    self.progress.emit(speed_mbps)
                    last_check = now
                    last_bytes = total_bytes

            if not samples:
                self.error.emit("Не удалось измерить скорость отдачи")
                return

            tail = samples[int(len(samples) * 0.3):] or samples
            avg = statistics.mean(tail)
            self.result.emit(avg)
        except Exception as e:
            self.error.emit(str(e))


# ============================================================
#  Круговой индикатор
# ============================================================

class GaugeWidget(QWidget):
    """Круговой спидометр."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(260, 260)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._value = 0.0         # 0..1
        self._big_text = "—"
        self._small_text = "Мбит/с"
        self._label = "ГОТОВ"
        self._color = "#6EC6FF"

    def set_value(self, value: float, big_text: str, small_text: str = "Мбит/с",
                   label: str = "", color: str = "#6EC6FF"):
        self._value = max(0.0, min(1.0, value))
        self._big_text = big_text
        self._small_text = small_text
        self._label = label
        self._color = color
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        side = min(self.width(), self.height()) - 20
        cx = self.width() / 2
        cy = self.height() / 2
        radius = side / 2

        # Фоновое кольцо
        pen = QPen(QColor(255, 255, 255, 25))
        pen.setWidth(16)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)

        from PySide6.QtCore import QRectF
        ring_rect = QRectF(cx - radius + 10, cy - radius + 10,
                            (radius - 10) * 2, (radius - 10) * 2)
        p.drawArc(ring_rect, 225 * 16, -270 * 16)

        # Прогресс
        if self._value > 0:
            pen = QPen(QColor(self._color))
            pen.setWidth(16)
            pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen)
            span = int(-270 * self._value * 16)
            p.drawArc(ring_rect, 225 * 16, span)

        # Метки шкалы
        p.setPen(QColor(255, 255, 255, 60))
        font_small = QFont()
        font_small.setPointSize(8)
        p.setFont(font_small)
        for i in range(11):
            angle_deg = 225 - i * 27
            import math
            angle_rad = math.radians(angle_deg)
            x1 = cx + math.cos(angle_rad) * (radius - 22)
            y1 = cy - math.sin(angle_rad) * (radius - 22)
            x2 = cx + math.cos(angle_rad) * (radius - 14)
            y2 = cy - math.sin(angle_rad) * (radius - 14)
            p.setPen(QPen(QColor(255, 255, 255, 60), 2))
            p.drawLine(QPointF(x1, y1), QPointF(x2, y2))

        # Большое число
        p.setPen(QColor("white"))
        font_big = QFont()
        font_big.setPointSize(44)
        font_big.setWeight(QFont.Light)
        p.setFont(font_big)
        big_rect = QRectF(cx - radius, cy - 40, radius * 2, 70)
        p.drawText(big_rect, Qt.AlignCenter, self._big_text)

        # Маленький текст
        p.setPen(QColor(255, 255, 255, 180))
        font2 = QFont()
        font2.setPointSize(11)
        p.setFont(font2)
        small_rect = QRectF(cx - radius, cy + 20, radius * 2, 20)
        p.drawText(small_rect, Qt.AlignCenter, self._small_text)

        # Метка
        if self._label:
            p.setPen(QColor(self._color))
            font3 = QFont()
            font3.setPointSize(10)
            font3.setBold(True)
            font3.setLetterSpacing(QFont.AbsoluteSpacing, 2)
            p.setFont(font3)
            label_rect = QRectF(cx - radius, cy + radius - 30, radius * 2, 20)
            p.drawText(label_rect, Qt.AlignCenter, self._label)


# ============================================================
#  Основное приложение
# ============================================================

def build():
    root = QWidget()
    root_layout = QVBoxLayout(root)
    root_layout.setContentsMargins(0, 0, 0, 0)
    root_layout.setSpacing(0)

    # ============================================================
    #  Верхняя панель — кнопка запуска
    # ============================================================
    top = QWidget()
    top.setFixedHeight(70)
    top.setStyleSheet("""
        background: rgba(255,255,255,0.04);
        border-bottom: 1px solid rgba(255,255,255,0.08);
    """)
    tl = QHBoxLayout(top)
    tl.setContentsMargins(20, 12, 20, 12)
    tl.setSpacing(14)

    title = QLabel("⚡  SpeedTest")
    title.setStyleSheet("color: white; font-size: 18px; font-weight: 600;")
    tl.addWidget(title)

    tl.addStretch(1)

    status_lbl = QLabel("Готов к запуску")
    status_lbl.setStyleSheet("color: rgba(255,255,255,0.55); font-size: 12px;")
    tl.addWidget(status_lbl)

    start_btn = QPushButton("▶  Начать тест")
    start_btn.setCursor(Qt.PointingHandCursor)
    start_btn.setFixedHeight(44)
    start_btn.setStyleSheet("""
        QPushButton {
            background: rgba(110,198,255,0.28);
            color: white;
            border: 1px solid rgba(110,198,255,0.65);
            border-radius: 12px;
            padding: 8px 28px;
            font-size: 14px;
            font-weight: 600;
        }
        QPushButton:hover { background: rgba(110,198,255,0.48); }
        QPushButton:disabled { background: rgba(255,255,255,0.04); color: rgba(255,255,255,0.35); border: 1px solid rgba(255,255,255,0.08); }
    """)
    tl.addWidget(start_btn)

    root_layout.addWidget(top)

    # ============================================================
    #  Основная область
    # ============================================================
    body = QWidget()
    body_layout = QHBoxLayout(body)
    body_layout.setContentsMargins(30, 30, 30, 30)
    body_layout.setSpacing(30)

    # ---- Спидометр ----
    gauge_box = QWidget()
    gauge_layout = QVBoxLayout(gauge_box)
    gauge_layout.setContentsMargins(0, 0, 0, 0)
    gauge_layout.setSpacing(16)

    gauge = GaugeWidget()
    gauge_layout.addWidget(gauge, 1)

    # Прогресс-бар под спидометром
    progress = QProgressBar()
    progress.setRange(0, 100)
    progress.setValue(0)
    progress.setTextVisible(False)
    progress.setFixedHeight(6)
    progress.setStyleSheet("""
        QProgressBar {
            background: rgba(255,255,255,0.10);
            border: none;
            border-radius: 3px;
        }
        QProgressBar::chunk {
            background: #6EC6FF;
            border-radius: 3px;
        }
    """)
    gauge_layout.addWidget(progress)

    body_layout.addWidget(gauge_box, 2)

    # ---- Правая панель — карточки ----
    right = QWidget()
    rl = QVBoxLayout(right)
    rl.setContentsMargins(0, 0, 0, 0)
    rl.setSpacing(10)

    def make_card(title_text: str, icon_name: str) -> tuple:
        card = QWidget()
        card.setStyleSheet("""
            QWidget {
                background: rgba(255,255,255,0.04);
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 14px;
            }
        """)
        cl = QHBoxLayout(card)
        cl.setContentsMargins(16, 12, 16, 12)
        cl.setSpacing(14)

        ic = QLabel()
        ic.setFixedSize(36, 36)
        ic.setAlignment(Qt.AlignCenter)
        ic.setPixmap(get_icon(icon_name, 24, "#6EC6FF"))
        ic.setStyleSheet("background: transparent; border: none;")
        cl.addWidget(ic)

        col = QVBoxLayout()
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(2)

        t = QLabel(title_text)
        t.setStyleSheet("""
            color: rgba(255,255,255,0.55);
            font-size: 10px;
            font-weight: 700;
            letter-spacing: 1.2px;
            background: transparent;
            border: none;
        """)
        col.addWidget(t)

        v = QLabel("—")
        v.setStyleSheet("""
            color: white;
            font-size: 16px;
            font-weight: 600;
            background: transparent;
            border: none;
        """)
        v.setWordWrap(True)
        col.addWidget(v)

        cl.addLayout(col, 1)
        return card, v

    # ---- Карточки ----
    ping_card, ping_val = make_card("PING", "clock")
    rl.addWidget(ping_card)

    download_card, download_val = make_card("ЗАГРУЗКА", "files")
    rl.addWidget(download_card)

    upload_card, upload_val = make_card("ОТДАЧА", "terminal")
    rl.addWidget(upload_card)

    ip_card, ip_val = make_card("IP-АДРЕС", "globe")
    rl.addWidget(ip_card)

    isp_card, isp_val = make_card("ПРОВАЙДЕР", "grid")
    rl.addWidget(isp_card)

    location_card, location_val = make_card("ЛОКАЦИЯ", "home")
    rl.addWidget(location_card)

    rl.addStretch(1)

    body_layout.addWidget(right, 1)

    root_layout.addWidget(body, 1)

    # ============================================================
    #  Нижняя панель — история
    # ============================================================
    bottom = QWidget()
    bottom.setFixedHeight(90)
    bottom.setStyleSheet("""
        background: rgba(255,255,255,0.03);
        border-top: 1px solid rgba(255,255,255,0.08);
    """)
    bl = QHBoxLayout(bottom)
    bl.setContentsMargins(20, 10, 20, 10)
    bl.setSpacing(10)

    history_title = QLabel("История тестов:")
    history_title.setStyleSheet("color: rgba(255,255,255,0.55); font-size: 12px; font-weight: 600;")
    bl.addWidget(history_title)

    history_lbl = QLabel("Пока пусто")
    history_lbl.setStyleSheet("""
        color: rgba(255,255,255,0.75);
        font-size: 12px;
        font-family: Consolas, monospace;
    """)
    history_lbl.setWordWrap(True)
    bl.addWidget(history_lbl, 1)

    root_layout.addWidget(bottom)

    # ============================================================
    #  Логика
    # ============================================================

    st = {
        "history": [],       # [{time, ping, dl, ul}]
        "current_test": "idle",
        "ping_worker": None,
        "ip_worker": None,
        "dl_worker": None,
        "ul_worker": None,
    }

    # ---- Обновление истории ----
    def refresh_history():
        if not st["history"]:
            history_lbl.setText("Пока пусто")
            return
        parts = []
        for h in st["history"][-5:]:
            t = h.get("time", "")[-5:]
            ping = f"{h.get('ping', 0):.0f}мс" if h.get("ping") else "—"
            dl = f"{h.get('dl', 0):.1f}" if h.get("dl") else "—"
            ul = f"{h.get('ul', 0):.1f}" if h.get("ul") else "—"
            parts.append(f"{t}  ↓{dl} ↑{ul}  ping {ping}")
        history_lbl.setText("    |    ".join(parts))

    # ---- Сохранение результата ----
    def push_history(ping=None, dl=None, ul=None):
        entry = {
            "time": datetime.now().isoformat(),
            "ping": ping or 0,
            "dl": dl or 0,
            "ul": ul or 0,
        }
        st["history"].append(entry)
        refresh_history()

    # ---- Тест ping ----
    def test_ping():
        status_lbl.setText("Измеряю задержку…")
        st["current_test"] = "ping"
        ping_val.setText("…")
        gauge.set_value(0, "…", "мс", "PING", "#6EC6FF")
        progress.setValue(10)

        worker = PingWorker("1.1.1.1", count=8)
        st["ping_worker"] = worker
        worker.result.connect(on_ping_done)
        worker.error.connect(on_test_error)
        worker.start()

    def on_ping_done(avg_ms, loss_pct):
        ping_val.setText(f"{avg_ms:.1f} мс" + (f"  ·  потеря {loss_pct:.0f}%"
                                                if loss_pct > 0 else ""))
        gauge.set_value(min(avg_ms / 200, 1.0), f"{avg_ms:.0f}",
                        "мс", "PING", "#6EC6FF")
        progress.setValue(30)
        QTimer.singleShot(400, test_ip_info)

    # ---- Тест IP ----
    def test_ip_info():
        status_lbl.setText("Определяю IP и провайдера…")
        worker = IpInfoWorker()
        st["ip_worker"] = worker
        worker.result.connect(on_ip_done)
        worker.error.connect(on_ip_error)
        worker.start()

    def on_ip_done(data):
        ip_val.setText(data.get("query", "—"))
        isp_val.setText(data.get("isp", data.get("org", "—")))
        location_val.setText(
            f"{data.get('city', '')}, {data.get('country', '')}".strip(", "))
        progress.setValue(40)
        QTimer.singleShot(300, test_download)

    def on_ip_error(err):
        ip_val.setText("не определён")
        isp_val.setText(err[:40])
        location_val.setText("—")
        progress.setValue(40)
        QTimer.singleShot(300, test_download)

    # ---- Тест загрузки ----
    def test_download():
        status_lbl.setText("Измеряю скорость загрузки… (10 сек)")
        st["current_test"] = "download"
        download_val.setText("…")
        gauge.set_value(0, "0.0", "Мбит/с", "ЗАГРУЗКА", "#6EE7B7")
        progress.setValue(50)

        worker = DownloadWorker(duration_sec=10)
        st["dl_worker"] = worker
        worker.progress.connect(on_dl_progress)
        worker.result.connect(on_dl_done)
        worker.error.connect(on_test_error)
        worker.start()

    def on_dl_progress(mbps):
        download_val.setText(f"{mbps:.2f} Мбит/с")
        # В спидометре нормируем: 100 Мбит/с → 1.0
        norm = min(mbps / 100.0, 1.0)
        gauge.set_value(norm, f"{mbps:.1f}", "Мбит/с", "ЗАГРУЗКА", "#6EE7B7")

    def on_dl_done(avg_mbps):
        download_val.setText(f"{avg_mbps:.2f} Мбит/с  ({fmt_bytes(avg_mbps * 1_000_000 / 8)})")
        progress.setValue(75)
        QTimer.singleShot(500, test_upload)

    # ---- Тест отдачи ----
    def test_upload():
        status_lbl.setText("Измеряю скорость отдачи… (10 сек)")
        st["current_test"] = "upload"
        upload_val.setText("…")
        gauge.set_value(0, "0.0", "Мбит/с", "ОТДАЧА", "#FFB86C")
        progress.setValue(80)

        worker = UploadWorker(duration_sec=10)
        st["ul_worker"] = worker
        worker.progress.connect(on_ul_progress)
        worker.result.connect(on_ul_done)
        worker.error.connect(on_test_error)
        worker.start()

    def on_ul_progress(mbps):
        upload_val.setText(f"{mbps:.2f} Мбит/с")
        norm = min(mbps / 50.0, 1.0)
        gauge.set_value(norm, f"{mbps:.1f}", "Мбит/с", "ОТДАЧА", "#FFB86C")

    def on_ul_done(avg_mbps):
        upload_val.setText(f"{avg_mbps:.2f} Мбит/с")
        progress.setValue(100)
        status_lbl.setText("✓ Тест завершён")

        # Собираем значения
        ping_text = ping_val.text().split(" ")[0]
        try:
            ping = float(ping_text.replace(",", "."))
        except ValueError:
            ping = 0
        dl = _parse_speed(download_val.text())
        ul = avg_mbps

        push_history(ping=ping, dl=dl, ul=ul)

        st["current_test"] = "idle"
        start_btn.setEnabled(True)
        start_btn.setText("▶  Повторить тест")

        # Уведомление
        d = _get_desktop(root)
        if d and hasattr(d, "notifications"):
            d.notifications.push("SpeedTest",
                f"↓{dl:.1f} Мбит/с  ↑{ul:.1f} Мбит/с  ping {ping:.0f}мс")

        # Возвращаем gauge к загрузке
        QTimer.singleShot(1500, lambda: gauge.set_value(
            min(dl / 100.0, 1.0), f"{dl:.1f}", "Мбит/с", "РЕЗУЛЬТАТ", "#6EE7B7"))

    def _parse_speed(text: str) -> float:
        try:
            first = text.split(" ")[0].replace(",", ".")
            return float(first)
        except Exception:
            return 0.0

    def on_test_error(err):
        status_lbl.setText(f"⚠ {err}")
        st["current_test"] = "idle"
        start_btn.setEnabled(True)

    # ---- Запуск полного теста ----
    def run_test():
        start_btn.setEnabled(False)
        start_btn.setText("⏳ Идёт тест…")
        # Сброс значений
        ping_val.setText("—")
        download_val.setText("—")
        upload_val.setText("—")
        ip_val.setText("—")
        isp_val.setText("—")
        location_val.setText("—")
        progress.setValue(0)
        status_lbl.setText("Начинаю тест…")
        QTimer.singleShot(200, test_ping)

    # ---- Связи ----
    start_btn.clicked.connect(run_test)

    # Стартовая загрузка истории
    refresh_history()

    return root