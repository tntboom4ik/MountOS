"""
MountOS — Часы.
Аналоговые + цифровые часы, будильник, таймер, секундомер.
"""
import time
from PySide6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QLabel,
                                QPushButton, QLineEdit, QTabWidget,
                                QListWidget, QListWidgetItem, QTimeEdit,
                                QMessageBox, QSpinBox, QSizePolicy, QFrame)
from PySide6.QtCore import Qt, QTimer, QTime, QDate, QPointF, QRectF, QSize
from PySide6.QtGui import (QPainter, QColor, QPen, QBrush, QFont, QIcon,
                            QPainterPath, QPolygonF)

from ui.icons import get_icon
from ui.settings_state import state

APP_NAME = "Часы"
APP_ICON = "globe"
APP_VERSION = "1.0"
APP_AUTHOR = "MountOS"


# ============================================================
#  Аналоговые часы (рисуются QPainter'ом)
# ============================================================

class AnalogClock(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(240, 240)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._t = QTime.currentTime()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(1000)

    def _tick(self):
        self._t = QTime.currentTime()
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        side = min(self.width(), self.height()) - 20
        cx = self.width() / 2
        cy = self.height() / 2
        r = side / 2

        # Циферблат
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(28, 34, 54, 200))
        p.drawEllipse(QPointF(cx, cy), r, r)

        p.setBrush(Qt.NoBrush)
        pen = QPen(QColor(255, 255, 255, 60))
        pen.setWidth(2)
        p.setPen(pen)
        p.drawEllipse(QPointF(cx, cy), r - 1, r - 1)

        # Метки
        accent = state().get("accent")
        for i in range(60):
            ang = i * 6
            if i % 5 == 0:
                p.setPen(QPen(QColor(accent), 3))
                p.drawLine(QPointF(cx + (r - 16) * self._sin(ang),
                                   cy - (r - 16) * self._cos(ang)),
                           QPointF(cx + (r - 6) * self._sin(ang),
                                   cy - (r - 6) * self._cos(ang)))
            else:
                p.setPen(QPen(QColor(255, 255, 255, 80), 1))
                p.drawLine(QPointF(cx + (r - 10) * self._sin(ang),
                                   cy - (r - 10) * self._cos(ang)),
                           QPointF(cx + (r - 6) * self._sin(ang),
                                   cy - (r - 6) * self._cos(ang)))

        # Цифры 12, 3, 6, 9
        p.setPen(QColor(255, 255, 255, 220))
        font = QFont()
        font.setPointSize(int(r / 9))
        font.setWeight(QFont.Light)
        p.setFont(font)
        for num, ang in [(12, 0), (3, 90), (6, 180), (9, 270)]:
            tx = cx + (r - 32) * self._sin(ang)
            ty = cy - (r - 32) * self._cos(ang)
            rect = QRectF(tx - 20, ty - 14, 40, 28)
            p.drawText(rect, Qt.AlignCenter, str(num))

        # Часы
        h = self._t.hour() % 12
        m = self._t.minute()
        s = self._t.second()

        hour_ang = (h + m / 60.0) * 30
        p.setPen(QPen(QColor(255, 255, 255, 240), 6, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(cx, cy),
                   QPointF(cx + (r * 0.5) * self._sin(hour_ang),
                           cy - (r * 0.5) * self._cos(hour_ang)))

        # Минуты
        min_ang = (m + s / 60.0) * 6
        p.setPen(QPen(QColor(255, 255, 255, 240), 4, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(cx, cy),
                   QPointF(cx + (r * 0.72) * self._sin(min_ang),
                           cy - (r * 0.72) * self._cos(min_ang)))

        # Секунды
        sec_ang = s * 6
        p.setPen(QPen(QColor(accent), 2, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(cx, cy),
                   QPointF(cx + (r * 0.82) * self._sin(sec_ang),
                           cy - (r * 0.82) * self._cos(sec_ang)))

        # Центр
        p.setBrush(QColor(accent))
        p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(cx, cy), 6, 6)
        p.setBrush(QColor(255, 255, 255, 240))
        p.drawEllipse(QPointF(cx, cy), 2.5, 2.5)

    @staticmethod
    def _sin(deg: float) -> float:
        import math
        return math.sin(math.radians(deg))

    @staticmethod
    def _cos(deg: float) -> float:
        import math
        return math.cos(math.radians(deg))


# ============================================================
#  Цифровые часы
# ============================================================

class DigitalClock(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(4)
        lay.setAlignment(Qt.AlignCenter)

        self.time_lbl = QLabel("--:--:--")
        self.time_lbl.setAlignment(Qt.AlignCenter)
        self.time_lbl.setStyleSheet("""
            color: white;
            font-size: 72px;
            font-weight: 200;
            letter-spacing: 6px;
        """)
        lay.addWidget(self.time_lbl)

        self.date_lbl = QLabel("—")
        self.date_lbl.setAlignment(Qt.AlignCenter)
        self.date_lbl.setStyleSheet("""
            color: rgba(255,255,255,0.55);
            font-size: 16px;
            letter-spacing: 2px;
        """)
        lay.addWidget(self.date_lbl)

        self.t = QTimer(self)
        self.t.timeout.connect(self._tick)
        self.t.start(1000)
        self._tick()

    def _tick(self):
        now = QTime.currentTime()
        self.time_lbl.setText(now.toString("HH:mm:ss"))
        months = ["января", "февраля", "марта", "апреля", "мая", "июня",
                  "июля", "августа", "сентября", "октября", "ноября", "декабря"]
        days = ["понедельник", "вторник", "среда", "четверг",
                "пятница", "суббота", "воскресенье"]
        d = QDate.currentDate()
        self.date_lbl.setText(
            f"{days[d.dayOfWeek() - 1]}, {d.day()} {months[d.month() - 1]} {d.year()}")


# ============================================================
#  Будильник
# ============================================================

class AlarmTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(14)

        title = QLabel("Будильники")
        title.setStyleSheet("color: white; font-size: 16px; font-weight: 600;")
        lay.addWidget(title)

        # Ввод
        add_row = QHBoxLayout()
        add_row.setSpacing(8)

        self.time_edit = QTimeEdit()
        self.time_edit.setDisplayFormat("HH:mm")
        self.time_edit.setTime(QTime.currentTime().addSecs(60))
        self.time_edit.setStyleSheet("""
            QTimeEdit {
                background: rgba(255,255,255,0.08);
                color: white;
                border: 1px solid rgba(255,255,255,0.15);
                border-radius: 10px;
                padding: 8px 12px;
                font-size: 18px;
                font-weight: 300;
                min-width: 90px;
            }
        """)
        add_row.addWidget(self.time_edit)

        self.label_edit = QLineEdit()
        self.label_edit.setPlaceholderText("Подпись (необязательно)")
        self.label_edit.setStyleSheet("""
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
        add_row.addWidget(self.label_edit, 1)

        add_btn = QPushButton("＋ Добавить")
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.setStyleSheet("""
            QPushButton {
                background: rgba(110,198,255,0.28);
                color: white;
                border: 1px solid rgba(110,198,255,0.60);
                border-radius: 10px;
                padding: 8px 16px;
                font-size: 13px;
                font-weight: 600;
            }
            QPushButton:hover { background: rgba(110,198,255,0.48); }
        """)
        add_row.addWidget(add_btn)

        lay.addLayout(add_row)

        # Список будильников
        self.list = QListWidget()
        self.list.setStyleSheet("""
            QListWidget {
                background: rgba(0,0,0,0.18);
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 12px;
                color: white;
                font-size: 13px;
                outline: none;
                padding: 4px;
            }
            QListWidget::item {
                padding: 10px 12px;
                border-radius: 8px;
            }
            QListWidget::item:hover { background: rgba(255,255,255,0.08); }
            QListWidget::item:selected { background: rgba(110,198,255,0.30); }
        """)
        lay.addWidget(self.list, 1)

        del_btn = QPushButton("Удалить выбранный")
        del_btn.setCursor(Qt.PointingHandCursor)
        del_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255,107,138,0.18);
                color: #FFA0B4;
                border: 1px solid rgba(255,107,138,0.45);
                border-radius: 10px;
                padding: 8px 16px;
                font-size: 12px;
            }
            QPushButton:hover { background: rgba(255,107,138,0.40); color: white; }
        """)
        lay.addWidget(del_btn)

        self._alarms = []  # [{time_str, label, triggered_today}]

        add_btn.clicked.connect(self._add_alarm)
        del_btn.clicked.connect(self._del_alarm)

        # Проверка срабатывания раз в секунду
        self._check_timer = QTimer(self)
        self._check_timer.timeout.connect(self._check)
        self._check_timer.start(1000)

    def _add_alarm(self):
        t = self.time_edit.time().toString("HH:mm")
        label = self.label_edit.text().strip()
        self._alarms.append({"time": t, "label": label, "last": ""})
        self._refresh()
        self.label_edit.clear()

    def _del_alarm(self):
        row = self.list.currentRow()
        if 0 <= row < len(self._alarms):
            del self._alarms[row]
            self._refresh()

    def _refresh(self):
        self.list.clear()
        for a in self._alarms:
            icon = get_icon("globe", 18, state().get("accent"))
            text = f"⏰  {a['time']}"
            if a["label"]:
                text += f"    · {a['label']}"
            item = QListWidgetItem(QIcon(icon), text)
            self.list.addItem(item)

    def _check(self):
        now = QTime.currentTime().toString("HH:mm")
        for a in self._alarms:
            if a["time"] == now and a["last"] != now:
                a["last"] = now
                self._trigger(a)

    def _trigger(self, alarm):
        title = "Будильник"
        msg = f"Сработал будильник на {alarm['time']}"
        if alarm["label"]:
            msg += f"\n{alarm['label']}"

        # Уведомление MountOS
        from PySide6.QtWidgets import QApplication
        for top in QApplication.topLevelWidgets():
            if hasattr(top, "notifications"):
                top.notifications.push(title, msg, duration_ms=6000)
                break
            ref = getattr(top, "desktop_ref", None)
            if ref is not None and hasattr(ref, "notifications"):
                ref.notifications.push(title, msg, duration_ms=6000)
                break


# ============================================================
#  Таймер
# ============================================================

class TimerTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(16)

        title = QLabel("Таймер")
        title.setStyleSheet("color: white; font-size: 16px; font-weight: 600;")
        lay.addWidget(title)

        # Большое время
        self.big_lbl = QLabel("00:00")
        self.big_lbl.setAlignment(Qt.AlignCenter)
        self.big_lbl.setStyleSheet("""
            color: white;
            font-size: 64px;
            font-weight: 200;
            letter-spacing: 4px;
        """)
        lay.addWidget(self.big_lbl)

        # Ввод
        input_row = QHBoxLayout()
        input_row.setSpacing(8)
        input_row.addStretch(1)

        def make_spin(label, maxv):
            w = QWidget()
            wl = QVBoxLayout(w)
            wl.setContentsMargins(0, 0, 0, 0)
            wl.setSpacing(2)
            l = QLabel(label)
            l.setAlignment(Qt.AlignCenter)
            l.setStyleSheet("color: rgba(255,255,255,0.55); font-size: 10px; letter-spacing: 1px;")
            wl.addWidget(l)
            sp = QSpinBox()
            sp.setRange(0, maxv)
            sp.setStyleSheet("""
                QSpinBox {
                    background: rgba(255,255,255,0.08);
                    color: white;
                    border: 1px solid rgba(255,255,255,0.15);
                    border-radius: 8px;
                    padding: 6px 10px;
                    font-size: 16px;
                    min-width: 60px;
                }
            """)
            wl.addWidget(sp)
            return w, sp

        w_h, self.sp_h = make_spin("ЧАСЫ", 23)
        w_m, self.sp_m = make_spin("МИНУТЫ", 59)
        w_s, self.sp_s = make_spin("СЕКУНДЫ", 59)
        input_row.addWidget(w_h)
        input_row.addWidget(w_m)
        input_row.addWidget(w_s)
        input_row.addStretch(1)
        lay.addLayout(input_row)

        # Кнопки управления
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_row.addStretch(1)

        self.start_btn = QPushButton("▶  Старт")
        self.start_btn.setCursor(Qt.PointingHandCursor)
        self.start_btn.setFixedHeight(42)
        self.start_btn.setStyleSheet(_accent_btn_style())
        btn_row.addWidget(self.start_btn)

        self.pause_btn = QPushButton("⏸  Пауза")
        self.pause_btn.setCursor(Qt.PointingHandCursor)
        self.pause_btn.setFixedHeight(42)
        self.pause_btn.setStyleSheet(_neutral_btn_style())
        btn_row.addWidget(self.pause_btn)

        self.reset_btn = QPushButton("↺  Сброс")
        self.reset_btn.setCursor(Qt.PointingHandCursor)
        self.reset_btn.setFixedHeight(42)
        self.reset_btn.setStyleSheet(_neutral_btn_style())
        btn_row.addWidget(self.reset_btn)

        btn_row.addStretch(1)
        lay.addLayout(btn_row)

        lay.addStretch(1)

        self._remaining = 0
        self._running = False

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.setInterval(1000)

        self.start_btn.clicked.connect(self._start)
        self.pause_btn.clicked.connect(self._pause)
        self.reset_btn.clicked.connect(self._reset)

    def _set_remaining(self, secs):
        self._remaining = max(0, secs)
        self._update_label()

    def _update_label(self):
        h = self._remaining // 3600
        m = (self._remaining % 3600) // 60
        s = self._remaining % 60
        if h > 0:
            self.big_lbl.setText(f"{h:02d}:{m:02d}:{s:02d}")
        else:
            self.big_lbl.setText(f"{m:02d}:{s:02d}")

    def _start(self):
        if self._remaining == 0:
            self._remaining = (self.sp_h.value() * 3600
                               + self.sp_m.value() * 60
                               + self.sp_s.value())
        if self._remaining <= 0:
            return
        self._running = True
        self._timer.start()

    def _pause(self):
        self._running = False
        self._timer.stop()

    def _reset(self):
        self._running = False
        self._timer.stop()
        self._remaining = 0
        self._update_label()
        self.big_lbl.setStyleSheet("""
            color: white;
            font-size: 64px;
            font-weight: 200;
            letter-spacing: 4px;
        """)

    def _tick(self):
        if self._remaining > 0:
            self._remaining -= 1
            self._update_label()
        if self._remaining == 0:
            self._timer.stop()
            self._running = False
            self.big_lbl.setStyleSheet("""
                color: #FFA0B4;
                font-size: 64px;
                font-weight: 300;
                letter-spacing: 4px;
            """)
            self.big_lbl.setText("Время!")
            self._notify()

    def _notify(self):
        from PySide6.QtWidgets import QApplication
        for top in QApplication.topLevelWidgets():
            if hasattr(top, "notifications"):
                top.notifications.push("Таймер", "Время вышло!", duration_ms=6000)
                return
            ref = getattr(top, "desktop_ref", None)
            if ref is not None and hasattr(ref, "notifications"):
                ref.notifications.push("Таймер", "Время вышло!", duration_ms=6000)
                return


# ============================================================
#  Секундомер
# ============================================================

class StopwatchTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(16)

        title = QLabel("Секундомер")
        title.setStyleSheet("color: white; font-size: 16px; font-weight: 600;")
        lay.addWidget(title)

        self.big_lbl = QLabel("00:00.00")
        self.big_lbl.setAlignment(Qt.AlignCenter)
        self.big_lbl.setStyleSheet("""
            color: white;
            font-size: 60px;
            font-weight: 200;
            letter-spacing: 2px;
        """)
        lay.addWidget(self.big_lbl)

        # Кнопки
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_row.addStretch(1)

        self.start_btn = QPushButton("▶  Старт")
        self.start_btn.setCursor(Qt.PointingHandCursor)
        self.start_btn.setFixedHeight(42)
        self.start_btn.setStyleSheet(_accent_btn_style())
        btn_row.addWidget(self.start_btn)

        self.lap_btn = QPushButton("⚑  Круг")
        self.lap_btn.setCursor(Qt.PointingHandCursor)
        self.lap_btn.setFixedHeight(42)
        self.lap_btn.setStyleSheet(_neutral_btn_style())
        btn_row.addWidget(self.lap_btn)

        self.reset_btn = QPushButton("↺  Сброс")
        self.reset_btn.setCursor(Qt.PointingHandCursor)
        self.reset_btn.setFixedHeight(42)
        self.reset_btn.setStyleSheet(_neutral_btn_style())
        btn_row.addWidget(self.reset_btn)

        btn_row.addStretch(1)
        lay.addLayout(btn_row)

        # Круги
        self.laps_list = QListWidget()
        self.laps_list.setStyleSheet("""
            QListWidget {
                background: rgba(0,0,0,0.18);
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 12px;
                color: white;
                font-size: 13px;
                outline: none;
                padding: 4px;
            }
            QListWidget::item {
                padding: 8px 12px;
                border-radius: 6px;
            }
            QListWidget::item:nth-child(even) {
                background: rgba(255,255,255,0.03);
            }
        """)
        lay.addWidget(self.laps_list, 1)

        self._elapsed_ms = 0
        self._running = False
        self._last_lap_ms = 0
        self._lap_num = 0

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.setInterval(30)

        self.start_btn.clicked.connect(self._toggle)
        self.lap_btn.clicked.connect(self._lap)
        self.reset_btn.clicked.connect(self._reset)

    def _fmt(self, ms):
        total_s = ms // 1000
        centis = (ms % 1000) // 10
        h = total_s // 3600
        m = (total_s % 3600) // 60
        s = total_s % 60
        if h > 0:
            return f"{h}:{m:02d}:{s:02d}.{centis:02d}"
        return f"{m:02d}:{s:02d}.{centis:02d}"

    def _toggle(self):
        if self._running:
            self._running = False
            self._timer.stop()
            self.start_btn.setText("▶  Старт")
        else:
            self._running = True
            self._timer.start()
            self.start_btn.setText("⏸  Пауза")

    def _tick(self):
        self._elapsed_ms += 30
        self.big_lbl.setText(self._fmt(self._elapsed_ms))

    def _lap(self):
        if not self._running:
            return
        self._lap_num += 1
        delta = self._elapsed_ms - self._last_lap_ms
        self._last_lap_ms = self._elapsed_ms
        item = QListWidgetItem(
            f"Круг {self._lap_num:02d}    Δ {self._fmt(delta)}    "
            f"Σ {self._fmt(self._elapsed_ms)}")
        self.laps_list.insertItem(0, item)

    def _reset(self):
        self._timer.stop()
        self._running = False
        self._elapsed_ms = 0
        self._last_lap_ms = 0
        self._lap_num = 0
        self.big_lbl.setText("00:00.00")
        self.start_btn.setText("▶  Старт")
        self.laps_list.clear()


# ============================================================
#  Стили
# ============================================================

def _accent_btn_style():
    return """
        QPushButton {
            background: rgba(110,198,255,0.28);
            color: white;
            border: 1px solid rgba(110,198,255,0.60);
            border-radius: 10px;
            padding: 8px 20px;
            font-size: 13px;
            font-weight: 600;
        }
        QPushButton:hover { background: rgba(110,198,255,0.48); }
    """


def _neutral_btn_style():
    return """
        QPushButton {
            background: rgba(255,255,255,0.08);
            color: white;
            border: 1px solid rgba(255,255,255,0.14);
            border-radius: 10px;
            padding: 8px 20px;
            font-size: 13px;
        }
        QPushButton:hover { background: rgba(255,255,255,0.20); }
    """


# ============================================================
#  Сборка
# ============================================================

def build():
    root = QWidget()
    h = QHBoxLayout(root)
    h.setContentsMargins(0, 0, 0, 0)
    h.setSpacing(0)

    tabs = QTabWidget()
    tabs.setStyleSheet("""
        QTabWidget::pane {
            background: transparent;
            border: none;
        }
        QTabBar::tab {
            background: rgba(255,255,255,0.04);
            color: rgba(255,255,255,0.65);
            border: 1px solid rgba(255,255,255,0.06);
            border-radius: 10px;
            padding: 8px 20px;
            margin: 6px 4px 6px 0;
            font-size: 12px;
            min-width: 100px;
        }
        QTabBar::tab:selected {
            background: rgba(110,198,255,0.22);
            color: white;
            border: 1px solid rgba(110,198,255,0.50);
        }
        QTabBar::tab:hover:!selected {
            background: rgba(255,255,255,0.10);
            color: white;
        }
    """)

    # Главная — аналоговые + цифровые
    main_tab = QWidget()
    ml = QHBoxLayout(main_tab)
    ml.setContentsMargins(20, 20, 20, 20)
    ml.setSpacing(20)
    ml.addWidget(AnalogClock(), 1)
    ml.addWidget(DigitalClock(), 1)

    tabs.addTab(main_tab,     "Часы")
    tabs.addTab(AlarmTab(),   "Будильник")
    tabs.addTab(TimerTab(),   "Таймер")
    tabs.addTab(StopwatchTab(), "Секундомер")

    h.addWidget(tabs, 1)
    return root