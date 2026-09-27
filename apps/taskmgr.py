"""
MountOS — Диспетчер задач.
Показывает реальные открытые окна MountOS, аптайм, память процесса.
Позволяет завершить приложение и посмотреть детали.
"""
import os
import sys
import time
import platform
from PySide6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QLabel,
                                QPushButton, QListWidget, QListWidgetItem,
                                QMessageBox, QProgressBar, QFrame,
                                QSizePolicy, QTabWidget, QTextEdit)
from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtGui import QIcon

from ui.icons import get_icon
from ui.settings_state import state

APP_NAME = "Диспетчер задач"
APP_ICON = "settings"
APP_VERSION = "1.0"
APP_AUTHOR = "MountOS"


_START_TIME = time.time()


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
#  Метрики процесса
# ============================================================

def _proc_memory_mb() -> float:
    """Реальная память процесса Python в МБ."""
    try:
        import psutil
        return psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024
    except ImportError:
        pass

    # Fallback без psutil — по платформам
    try:
        if sys.platform.startswith("win"):
            import ctypes
            from ctypes import wintypes

            class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
                _fields_ = [
                    ("cb", ctypes.c_ulong),
                    ("PageFaultCount", ctypes.c_ulong),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                ]

            ctypes.windll.psapi.GetProcessMemoryInfo(
                ctypes.windll.kernel32.GetCurrentProcess(),
                ctypes.byref(PROCESS_MEMORY_COUNTERS()),
                ctypes.sizeof(PROCESS_MEMORY_COUNTERS))
            pmc = PROCESS_MEMORY_COUNTERS()
            pmc.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
            ctypes.windll.psapi.GetProcessMemoryInfo(
                ctypes.windll.kernel32.GetCurrentProcess(),
                ctypes.byref(pmc), pmc.cb)
            return pmc.WorkingSetSize / 1024 / 1024

        elif sys.platform.startswith("linux"):
            with open("/proc/self/statm", "r") as f:
                pages = int(f.read().split()[1])
            return pages * os.sysconf("SC_PAGE_SIZE") / 1024 / 1024
    except Exception:
        pass

    return 0.0


def _proc_cpu_percent() -> float:
    """CPU % (только с psutil)."""
    try:
        import psutil
        return psutil.Process(os.getpid()).cpu_percent(interval=None)
    except Exception:
        return 0.0


def _fmt_uptime(secs: float) -> str:
    secs = int(secs)
    d = secs // 86400
    h = (secs % 86400) // 3600
    m = (secs % 3600) // 60
    s = secs % 60
    if d > 0:
        return f"{d}д {h:02d}:{m:02d}:{s:02d}"
    return f"{h:02d}:{m:02d}:{s:02d}"


# ============================================================
#  Основное приложение
# ============================================================

def build():
    root = QWidget()
    h = QHBoxLayout(root)
    h.setContentsMargins(0, 0, 0, 0)
    h.setSpacing(0)

    # ---------- Левая панель: список окон ----------
    side = QWidget()
    side.setFixedWidth(280)
    side.setStyleSheet("""
        background: rgba(255,255,255,0.04);
        border-right: 1px solid rgba(255,255,255,0.08);
    """)
    sl = QVBoxLayout(side)
    sl.setContentsMargins(12, 14, 12, 14)
    sl.setSpacing(8)

    header = QLabel("Открытые окна")
    header.setStyleSheet("color: white; font-size: 14px; font-weight: 600; padding: 2px 4px;")
    sl.addWidget(header)

    windows_list = QListWidget()
    windows_list.setStyleSheet("""
        QListWidget {
            background: rgba(0,0,0,0.18);
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 10px;
            color: white;
            font-size: 12px;
            outline: none;
            padding: 4px;
        }
        QListWidget::item {
            padding: 8px 10px;
            border-radius: 6px;
        }
        QListWidget::item:hover { background: rgba(255,255,255,0.08); }
        QListWidget::item:selected { background: rgba(110,198,255,0.30); }
    """)
    windows_list.setIconSize(QSize(20, 20))
    sl.addWidget(windows_list, 1)

    # Кнопки над списком
    btn_row = QHBoxLayout()
    btn_row.setSpacing(6)

    refresh_btn = QPushButton("⟳  Обновить")
    refresh_btn.setCursor(Qt.PointingHandCursor)
    refresh_btn.setFixedHeight(32)
    refresh_btn.setStyleSheet("""
        QPushButton {
            background: rgba(255,255,255,0.08);
            color: white;
            border: 1px solid rgba(255,255,255,0.14);
            border-radius: 8px;
            font-size: 11px;
        }
        QPushButton:hover { background: rgba(255,255,255,0.20); }
    """)
    btn_row.addWidget(refresh_btn, 1)

    kill_btn = QPushButton("✕  Завершить")
    kill_btn.setCursor(Qt.PointingHandCursor)
    kill_btn.setFixedHeight(32)
    kill_btn.setStyleSheet("""
        QPushButton {
            background: rgba(255,107,138,0.18);
            color: #FFA0B4;
            border: 1px solid rgba(255,107,138,0.45);
            border-radius: 8px;
            font-size: 11px;
        }
        QPushButton:hover { background: rgba(255,107,138,0.40); color: white; }
    """)
    btn_row.addWidget(kill_btn, 1)

    sl.insertLayout(1, btn_row)

    h.addWidget(side)

    # ---------- Правая область: статистика ----------
    right = QWidget()
    rl = QVBoxLayout(right)
    rl.setContentsMargins(20, 18, 20, 18)
    rl.setSpacing(14)

    title = QLabel("Диспетчер задач MountOS")
    title.setStyleSheet("color: white; font-size: 16px; font-weight: 600;")
    rl.addWidget(title)

    # ---- Карточки метрик ----
    metrics = QWidget()
    ml = QHBoxLayout(metrics)
    ml.setContentsMargins(0, 0, 0, 0)
    ml.setSpacing(10)

    def make_metric(title_text: str, value_text: str):
        card = QWidget()
        card.setStyleSheet("""
            QWidget {
                background: rgba(255,255,255,0.05);
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 14px;
            }
        """)
        cl = QVBoxLayout(card)
        cl.setContentsMargins(14, 12, 14, 12)
        cl.setSpacing(4)

        t = QLabel(title_text.upper())
        t.setStyleSheet("""
            color: rgba(255,255,255,0.45);
            font-size: 10px;
            font-weight: 700;
            letter-spacing: 1.4px;
            background: transparent;
            border: none;
        """)
        cl.addWidget(t)

        v = QLabel(value_text)
        v.setStyleSheet("""
            color: white;
            font-size: 22px;
            font-weight: 300;
            background: transparent;
            border: none;
        """)
        cl.addWidget(v)
        return card, v

    card_uptime, val_uptime = make_metric("Аптайм", "—")
    card_mem, val_mem = make_metric("Память Python", "—")
    card_wins, val_wins = make_metric("Окон", "—")
    card_apps, val_apps = make_metric("Приложений", "—")

    ml.addWidget(card_uptime)
    ml.addWidget(card_mem)
    ml.addWidget(card_wins)
    ml.addWidget(card_apps)
    rl.addWidget(metrics)

    # ---- CPU bar ----
    cpu_box = QWidget()
    cpu_box.setStyleSheet("""
        QWidget {
            background: rgba(255,255,255,0.04);
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 14px;
        }
    """)
    cbl = QVBoxLayout(cpu_box)
    cbl.setContentsMargins(14, 12, 14, 14)
    cbl.setSpacing(8)

    cpu_hdr = QHBoxLayout()
    cpu_lbl = QLabel("Загрузка ЦП процесса")
    cpu_lbl.setStyleSheet("""
        color: rgba(255,255,255,0.85);
        font-size: 12px;
        background: transparent;
        border: none;
    """)
    cpu_hdr.addWidget(cpu_lbl)
    cpu_hdr.addStretch(1)
    cpu_val = QLabel("—")
    cpu_val.setStyleSheet("""
        color: white;
        font-size: 12px;
        font-weight: 600;
        background: transparent;
        border: none;
    """)
    cpu_hdr.addWidget(cpu_val)
    cbl.addLayout(cpu_hdr)

    cpu_bar = QProgressBar()
    cpu_bar.setRange(0, 100)
    cpu_bar.setValue(0)
    cpu_bar.setTextVisible(False)
    cpu_bar.setFixedHeight(10)
    cpu_bar.setStyleSheet("""
        QProgressBar {
            background: rgba(255,255,255,0.10);
            border: none;
            border-radius: 5px;
        }
        QProgressBar::chunk {
            background: #6EC6FF;
            border-radius: 5px;
        }
    """)
    cbl.addWidget(cpu_bar)

    rl.addWidget(cpu_box)

    # ---- Информация о системе ----
    sys_title = QLabel("Система")
    sys_title.setStyleSheet("""
        color: rgba(255,255,255,0.55);
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 1.4px;
        padding: 12px 2px 4px 2px;
    """)
    rl.addWidget(sys_title)

    sys_info = QTextEdit()
    sys_info.setReadOnly(True)
    sys_info.setStyleSheet("""
        QTextEdit {
            background: rgba(0,0,0,0.20);
            color: rgba(255,255,255,0.85);
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 12px;
            padding: 12px;
            font-family: Consolas, monospace;
            font-size: 12px;
        }
    """)
    rl.addWidget(sys_info, 1)

    h.addWidget(right, 1)

    # ============================================================
    #  Логика
    # ============================================================

    def refresh_windows():
        windows_list.clear()
        d = _get_desktop(root)
        wins = getattr(d, "windows", []) if d else []

        for idx, win in enumerate(wins):
            try:
                app_id = getattr(win, "app_id", "") or "unknown"
                title_txt = win.windowTitle().replace("MountOS — ", "")
                if not title_txt:
                    title_txt = app_id
                vis = "видимо" if win.isVisible() else "скрыто"
                if win.isMinimized():
                    vis = "свёрнуто"

                item = QListWidgetItem(
                    QIcon(get_icon(app_id if app_id else "files", 20,
                                   state().get("accent"))),
                    f"{title_txt}    · {vis}")
                item.setData(Qt.UserRole, idx)
                windows_list.addItem(item)
            except RuntimeError:
                continue

    def refresh_metrics():
        uptime = time.time() - _START_TIME
        val_uptime.setText(_fmt_uptime(uptime))

        mem = _proc_memory_mb()
        val_mem.setText(f"{mem:.1f} МБ" if mem > 0 else "—")

        d = _get_desktop(root)
        wins = getattr(d, "windows", []) if d else []
        val_wins.setText(str(len(wins)))

        reg = getattr(d, "registry", None) if d else None
        if reg:
            val_apps.setText(str(len(reg.apps)))
        else:
            val_apps.setText("—")

        cpu = _proc_cpu_percent()
        cpu_val.setText(f"{cpu:.0f}%")
        cpu_bar.setValue(int(min(cpu, 100)))

    def refresh_sysinfo():
        import PySide6
        d = _get_desktop(root)
        reg = getattr(d, "registry", None) if d else None

        lines = [
            f"Платформа:     {platform.system()} {platform.release()}",
            f"Архитектура:   {platform.machine()}",
            f"Python:        {platform.python_version()}",
            f"PySide6:       {PySide6.__version__}",
            f"PID:           {os.getpid()}",
            f"Исполняемый:   {sys.executable}",
            f"Рабочая папка: {os.getcwd()}",
        ]
        if reg:
            lines.append(f"Приложений:    {len(reg.apps)}")
            builtin = sum(1 for a in reg.apps.values() if a.builtin)
            custom = len(reg.apps) - builtin
            lines.append(f"  · системных:      {builtin}")
            lines.append(f"  · пользовательских: {custom}")
        try:
            from system.paths import USER_DATA, PLATFORM
            lines.append(f"PLATFORM:      {PLATFORM}")
            lines.append(f"USER_DATA:     {USER_DATA}")
        except Exception:
            pass

        sys_info.setPlainText("\n".join(lines))

    # ---- Кнопки ----
    def kill_selected():
        item = windows_list.currentItem()
        if item is None:
            QMessageBox.information(root, "Диспетчер задач",
                                    "Выбери окно слева.")
            return
        idx = int(item.data(Qt.UserRole))
        d = _get_desktop(root)
        if d is None:
            return
        wins = getattr(d, "windows", [])
        if idx < 0 or idx >= len(wins):
            return
        win = wins[idx]
        try:
            title = win.windowTitle().replace("MountOS — ", "")
        except RuntimeError:
            refresh_windows()
            return

        ans = QMessageBox.question(
            root, "Завершить приложение",
            f"Завершить окно «{title}»?\n\nНесохранённые данные будут потеряны.",
            QMessageBox.Yes | QMessageBox.No)
        if ans == QMessageBox.Yes:
            try:
                win.close()
            except RuntimeError:
                pass
            refresh_windows()

    refresh_btn.clicked.connect(lambda: (refresh_windows(), refresh_metrics()))
    kill_btn.clicked.connect(kill_selected)

    # Автообновление
    auto_timer = QTimer(root)
    auto_timer.setInterval(1500)

    def tick():
        refresh_metrics()
        refresh_windows()

    auto_timer.timeout.connect(tick)
    auto_timer.start()

    # Двойной клик по окну — фокус на него
    def focus_selected(item):
        idx = int(item.data(Qt.UserRole))
        d = _get_desktop(root)
        if d is None:
            return
        wins = getattr(d, "windows", [])
        if 0 <= idx < len(wins):
            w = wins[idx]
            try:
                if w.isMinimized():
                    w.showNormal()
                w.raise_()
                w.activateWindow()
            except RuntimeError:
                pass

    windows_list.itemDoubleClicked.connect(focus_selected)

    # Первичная загрузка
    refresh_windows()
    refresh_metrics()
    refresh_sysinfo()

    return root