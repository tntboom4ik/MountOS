from PySide6.QtWidgets import QLabel, QWidget, QVBoxLayout, QHBoxLayout, QProgressBar
from PySide6.QtCore import Qt, QTimer, QTime, QDate
from PySide6.QtGui import QFont

from ui.widget_base import DesktopWidget


# ---------- Часы ----------

class ClockWidget(DesktopWidget):
    def __init__(self, parent):
        super().__init__(parent, "clock", "ЧАСЫ", width=240, height=150)

        self.time_lbl = QLabel()
        self.time_lbl.setStyleSheet("""
            color: white;
            font-size: 40px;
            font-weight: 200;
            letter-spacing: 3px;
        """)
        self.time_lbl.setAlignment(Qt.AlignCenter)
        self.body_layout.addWidget(self.time_lbl)

        self.date_lbl = QLabel()
        self.date_lbl.setStyleSheet("color: rgba(255,255,255,0.55); font-size: 12px; letter-spacing: 1px;")
        self.date_lbl.setAlignment(Qt.AlignCenter)
        self.body_layout.addWidget(self.date_lbl)

        self.t = QTimer(self); self.t.timeout.connect(self._tick); self.t.start(1000)
        self._tick()

    def _tick(self):
        self.time_lbl.setText(QTime.currentTime().toString("HH:mm"))
        months = ["янв","фев","мар","апр","мая","июн",
                  "июл","авг","сен","окт","ноя","дек"]
        d = QDate.currentDate()
        days = ["пн","вт","ср","чт","пт","сб","вс"]
        self.date_lbl.setText(
            f"{days[d.dayOfWeek()-1]}, {d.day()} {months[d.month()-1]} {d.year()}")


# ---------- Система ----------

class SystemWidget(DesktopWidget):
    def __init__(self, parent):
        super().__init__(parent, "system", "СИСТЕМА", width=240, height=170)

        self.cpu_lbl = QLabel("ЦП")
        self.cpu_lbl.setStyleSheet("color: rgba(255,255,255,0.85); font-size: 12px;")
        self.body_layout.addWidget(self.cpu_lbl)

        self.cpu_bar = QProgressBar()
        self._bar_style(self.cpu_bar)
        self.body_layout.addWidget(self.cpu_bar)

        self.ram_lbl = QLabel("ОЗУ")
        self.ram_lbl.setStyleSheet("color: rgba(255,255,255,0.85); font-size: 12px;")
        self.body_layout.addWidget(self.ram_lbl)

        self.ram_bar = QProgressBar()
        self._bar_style(self.ram_bar)
        self.body_layout.addWidget(self.ram_bar)

        self.t = QTimer(self); self.t.timeout.connect(self._update); self.t.start(2000)
        self._update()

    def _bar_style(self, bar):
        bar.setFixedHeight(8)
        bar.setTextVisible(False)
        bar.setStyleSheet("""
            QProgressBar {
                background: rgba(255,255,255,0.10);
                border: none;
                border-radius: 4px;
            }
            QProgressBar::chunk {
                background: #6EC6FF;
                border-radius: 4px;
            }
        """)

    def _update(self):
        import psutil  # если нет — fallback
        try:
            cpu = int(psutil.cpu_percent(interval=None))
            ram = int(psutil.virtual_memory().percent)
        except Exception:
            import random
            cpu = random.randint(5, 40)
            ram = random.randint(30, 70)
        self.cpu_bar.setValue(cpu)
        self.ram_bar.setValue(ram)
        self.cpu_lbl.setText(f"ЦП   {cpu}%")
        self.ram_lbl.setText(f"ОЗУ  {ram}%")


# ---------- Заметка дня ----------

class StickyNoteWidget(DesktopWidget):
    def __init__(self, parent):
        super().__init__(parent, "sticky", "ЗАМЕТКА ДНЯ", width=260, height=160)

        self.lbl = QLabel("Двойной клик — редактировать.\n\n"
                          "Заметка сохраняется автоматически в VFS.")
        self.lbl.setWordWrap(True)
        self.lbl.setStyleSheet("color: rgba(255,255,255,0.85); font-size: 12px;")
        self.body_layout.addWidget(self.lbl, 1)

        self._load()

    def _load(self):
        try:
            from ui.settings_state import state
            vfs = _get_vfs()
            if vfs:
                text = vfs.read_text("/Notes/sticky.txt", "")
                if text:
                    self.lbl.setText(text[:400])
        except Exception:
            pass

    def mouseDoubleClickEvent(self, e):
        from PySide6.QtWidgets import QInputDialog
        vfs = _get_vfs()
        cur = self.lbl.text()
        text, ok = QInputDialog.getMultiLineText(self, "Заметка дня", "Текст:", cur)
        if ok and vfs:
            vfs.write_text("/Notes/sticky.txt", text)
            self.lbl.setText(text[:400] if text else "Пусто")


# ---------- Погода (демо) ----------

class WeatherWidget(DesktopWidget):
    def __init__(self, parent):
        super().__init__(parent, "weather", "ПОГОДА", width=220, height=140)

        self.temp = QLabel("+18°")
        self.temp.setStyleSheet("color: white; font-size: 38px; font-weight: 200;")
        self.temp.setAlignment(Qt.AlignCenter)
        self.body_layout.addWidget(self.temp)

        self.desc = QLabel("Ясно · Москва")
        self.desc.setStyleSheet("color: rgba(255,255,255,0.55); font-size: 12px;")
        self.desc.setAlignment(Qt.AlignCenter)
        self.body_layout.addWidget(self.desc)


# ---------- Быстрые действия ----------

class QuickActionsWidget(DesktopWidget):
    def __init__(self, parent):
        super().__init__(parent, "quick", "БЫСТРЫЕ ДЕЙСТВИЯ", width=240, height=140)

        grid = QHBoxLayout()
        for label in ["Файлы", "Терминал", "Заметки"]:
            from PySide6.QtWidgets import QPushButton
            b = QPushButton(label)
            b.setCursor(Qt.PointingHandCursor)
            b.setFixedHeight(36)
            b.setStyleSheet("""
                QPushButton {
                    background: rgba(255,255,255,0.10);
                    color: white;
                    border: 1px solid rgba(255,255,255,0.16);
                    border-radius: 10px;
                    padding: 6px 10px;
                    font-size: 11px;
                }
                QPushButton:hover { background: rgba(255,255,255,0.22); }
                QPushButton:pressed { background: rgba(110,198,255,0.45); }
            """)
            b.clicked.connect(lambda _, n=label: _launch(n))
            grid.addWidget(b)
        self.body_layout.addLayout(grid)
        self.body_layout.addStretch(1)


def _get_vfs():
    from PySide6.QtWidgets import QApplication
    for w in QApplication.topLevelWidgets():
        if hasattr(w, "vfs"):
            return w.vfs
    return None


def _launch(name):
    from PySide6.QtWidgets import QApplication
    ids = {"Файлы": "files", "Терминал": "terminal", "Заметки": "notes"}
    for w in QApplication.topLevelWidgets():
        if hasattr(w, "open_app"):
            w.open_app(ids.get(name, name))
            return


WIDGET_FACTORY = {
    "clock":   ClockWidget,
    "system":  SystemWidget,
    "sticky":  StickyNoteWidget,
    "weather": WeatherWidget,
    "quick":   QuickActionsWidget,
}


WIDGET_NAMES = {
    "clock":   "Часы",
    "system":  "Система",
    "sticky":  "Заметка дня",
    "weather": "Погода",
    "quick":   "Быстрые действия",
}