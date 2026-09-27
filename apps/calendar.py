"""
MountOS — Календарь.
Сетка дней на месяц, навигация по месяцам/годам,
добавление и удаление событий, сохранение в VFS.
"""
import os
import json
from PySide6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QLabel,
                                QPushButton, QGridLayout, QListWidget,
                                QListWidgetItem, QLineEdit, QTimeEdit,
                                QMessageBox, QSizePolicy, QFrame, QComboBox)
from PySide6.QtCore import Qt, QDate, QTime, QSize
from PySide6.QtGui import QIcon

from ui.icons import get_icon
from ui.settings_state import state

APP_NAME = "Календарь"
APP_ICON = "globe"
APP_VERSION = "1.0"
APP_AUTHOR = "MountOS"


MONTHS_RU = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
             "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]
DAYS_RU = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]


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
#  Кнопка дня
# ============================================================

class DayButton(QPushButton):
    def __init__(self, date: QDate, on_click, events_count=0, parent=None):
        super().__init__(parent)
        self.date = date
        self.on_click = on_click
        self.events_count = events_count

        self.setFixedHeight(56)
        self.setCursor(Qt.PointingHandCursor)

        self._update_text()
        self._update_style()

    def _update_text(self):
        txt = str(self.date.day())
        if self.events_count > 0:
            txt += f"\n• {self.events_count}"
        self.setText(txt)

    def set_active(self, active: bool):
        self._active = active
        self._update_style()

    def _update_style(self):
        today = QDate.currentDate()
        is_today = (self.date == today)
        is_active = getattr(self, "_active", False)

        if is_active:
            bg = "rgba(110,198,255,0.35)"
            border = "2px solid rgba(110,198,255,0.9)"
        elif is_today:
            bg = "rgba(110,198,255,0.18)"
            border = "1px solid rgba(110,198,255,0.65)"
        else:
            bg = "rgba(255,255,255,0.04)"
            border = "1px solid rgba(255,255,255,0.08)"

        self.setStyleSheet(f"""
            QPushButton {{
                background: {bg};
                color: white;
                border: {border};
                border-radius: 10px;
                font-size: 13px;
                font-weight: 500;
                text-align: center;
                padding: 2px;
            }}
            QPushButton:hover {{
                background: rgba(255,255,255,0.18);
                border: 1px solid rgba(255,255,255,0.35);
            }}
            QPushButton:pressed {{
                background: rgba(110,198,255,0.55);
            }}
        """)


# ============================================================
#  Основное приложение
# ============================================================

def build():
    root = QWidget()
    h = QHBoxLayout(root)
    h.setContentsMargins(0, 0, 0, 0)
    h.setSpacing(0)

    # ---------- Левая панель: сетка календаря ----------
    left = QWidget()
    left.setStyleSheet("""
        background: rgba(255,255,255,0.03);
        border-right: 1px solid rgba(255,255,255,0.08);
    """)
    ll = QVBoxLayout(left)
    ll.setContentsMargins(18, 16, 18, 16)
    ll.setSpacing(12)

    # Верхняя панель: месяц + навигация
    top_row = QHBoxLayout()
    top_row.setSpacing(8)

    prev_year = QPushButton("«")
    prev_year.setFixedSize(32, 32)
    prev_year.setToolTip("Предыдущий год")
    prev_year.setCursor(Qt.PointingHandCursor)
    prev_year.setStyleSheet(_icon_btn_style())
    top_row.addWidget(prev_year)

    prev_month = QPushButton("‹")
    prev_month.setFixedSize(32, 32)
    prev_month.setToolTip("Предыдущий месяц")
    prev_month.setCursor(Qt.PointingHandCursor)
    prev_month.setStyleSheet(_icon_btn_style())
    top_row.addWidget(prev_month)

    month_lbl = QLabel()
    month_lbl.setAlignment(Qt.AlignCenter)
    month_lbl.setStyleSheet("""
        color: white;
        font-size: 16px;
        font-weight: 600;
        letter-spacing: 0.5px;
    """)
    top_row.addWidget(month_lbl, 1)

    next_month = QPushButton("›")
    next_month.setFixedSize(32, 32)
    next_month.setToolTip("Следующий месяц")
    next_month.setCursor(Qt.PointingHandCursor)
    next_month.setStyleSheet(_icon_btn_style())
    top_row.addWidget(next_month)

    next_year = QPushButton("»")
    next_year.setFixedSize(32, 32)
    next_year.setToolTip("Следующий год")
    next_year.setCursor(Qt.PointingHandCursor)
    next_year.setStyleSheet(_icon_btn_style())
    top_row.addWidget(next_year)

    ll.addLayout(top_row)

    today_btn = QPushButton("Сегодня")
    today_btn.setCursor(Qt.PointingHandCursor)
    today_btn.setFixedHeight(30)
    today_btn.setStyleSheet("""
        QPushButton {
            background: rgba(255,255,255,0.06);
            color: white;
            border: 1px solid rgba(255,255,255,0.12);
            border-radius: 8px;
            font-size: 11px;
        }
        QPushButton:hover { background: rgba(255,255,255,0.18); }
    """)
    ll.addWidget(today_btn)

    # Дни недели
    days_header = QWidget()
    dh = QGridLayout(days_header)
    dh.setContentsMargins(0, 0, 0, 0)
    dh.setSpacing(4)
    for i, d in enumerate(DAYS_RU):
        l = QLabel(d)
        l.setAlignment(Qt.AlignCenter)
        color = "#FF6B8A" if i >= 5 else "rgba(255,255,255,0.55)"
        l.setStyleSheet(f"color: {color}; font-size: 11px; font-weight: 700;")
        dh.addWidget(l, 0, i)
    ll.addWidget(days_header)

    # Сетка дней
    grid_widget = QWidget()
    grid = QGridLayout(grid_widget)
    grid.setContentsMargins(0, 0, 0, 0)
    grid.setSpacing(4)
    ll.addWidget(grid_widget, 1)

    ll.addStretch(0)

    h.addWidget(left, 3)

    # ---------- Правая панель: события выбранного дня ----------
    right = QWidget()
    rl = QVBoxLayout(right)
    rl.setContentsMargins(18, 16, 18, 16)
    rl.setSpacing(10)

    selected_lbl = QLabel("—")
    selected_lbl.setStyleSheet("""
        color: white;
        font-size: 15px;
        font-weight: 600;
    """)
    rl.addWidget(selected_lbl)

    # Форма добавления
    add_box = QWidget()
    add_box.setStyleSheet("""
        QWidget {
            background: rgba(255,255,255,0.04);
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 12px;
        }
    """)
    al = QVBoxLayout(add_box)
    al.setContentsMargins(12, 10, 12, 10)
    al.setSpacing(8)

    add_lbl = QLabel("Новое событие")
    add_lbl.setStyleSheet("""
        color: rgba(255,255,255,0.55);
        font-size: 10px;
        font-weight: 700;
        letter-spacing: 1.4px;
        background: transparent;
        border: none;
    """)
    al.addWidget(add_lbl)

    form_row = QHBoxLayout()
    form_row.setSpacing(6)

    time_edit = QTimeEdit()
    time_edit.setDisplayFormat("HH:mm")
    time_edit.setTime(QTime.currentTime())
    time_edit.setStyleSheet("""
        QTimeEdit {
            background: rgba(255,255,255,0.08);
            color: white;
            border: 1px solid rgba(255,255,255,0.15);
            border-radius: 8px;
            padding: 6px 8px;
            font-size: 12px;
            min-width: 70px;
        }
    """)
    form_row.addWidget(time_edit)

    text_edit = QLineEdit()
    text_edit.setPlaceholderText("Что?")
    text_edit.setStyleSheet("""
        QLineEdit {
            background: rgba(255,255,255,0.08);
            color: white;
            border: 1px solid rgba(255,255,255,0.15);
            border-radius: 8px;
            padding: 6px 10px;
            font-size: 12px;
        }
        QLineEdit:focus { border: 1px solid rgba(110,198,255,0.6); }
    """)
    form_row.addWidget(text_edit, 1)

    add_btn = QPushButton("＋")
    add_btn.setFixedSize(34, 34)
    add_btn.setCursor(Qt.PointingHandCursor)
    add_btn.setToolTip("Добавить")
    add_btn.setStyleSheet("""
        QPushButton {
            background: rgba(110,198,255,0.28);
            color: white;
            border: 1px solid rgba(110,198,255,0.60);
            border-radius: 8px;
            font-size: 16px;
            font-weight: 600;
        }
        QPushButton:hover { background: rgba(110,198,255,0.50); }
    """)
    form_row.addWidget(add_btn)

    al.addLayout(form_row)
    rl.addWidget(add_box)

    # Список событий
    events_lbl = QLabel("События дня")
    events_lbl.setStyleSheet("""
        color: rgba(255,255,255,0.55);
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 1.4px;
        padding-top: 4px;
    """)
    rl.addWidget(events_lbl)

    events_list = QListWidget()
    events_list.setStyleSheet("""
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
            padding: 8px 10px;
            border-radius: 6px;
        }
        QListWidget::item:hover { background: rgba(255,255,255,0.08); }
        QListWidget::item:selected { background: rgba(110,198,255,0.30); }
    """)
    rl.addWidget(events_list, 1)

    del_btn = QPushButton("Удалить событие")
    del_btn.setCursor(Qt.PointingHandCursor)
    del_btn.setFixedHeight(32)
    del_btn.setStyleSheet("""
        QPushButton {
            background: rgba(255,107,138,0.18);
            color: #FFA0B4;
            border: 1px solid rgba(255,107,138,0.45);
            border-radius: 10px;
            font-size: 11px;
        }
        QPushButton:hover { background: rgba(255,107,138,0.40); color: white; }
    """)
    rl.addWidget(del_btn)

    h.addWidget(right, 2)

    # ============================================================
    #  Логика
    # ============================================================

    state_obj = {
        "view_year":  QDate.currentDate().year(),
        "view_month": QDate.currentDate().month(),
        "selected":   QDate.currentDate(),
        "events":     {},   # {"YYYY-MM-DD": [{"time": "HH:MM", "text": "..."}]}
    }

    # ---- Загрузка / сохранение событий ----

    EVENTS_PATH = "/Notes/calendar_events.json"

    def load_events():
        vfs = _get_vfs(root)
        if vfs is None:
            return
        try:
            raw = vfs.read_text(EVENTS_PATH, "{}")
            data = json.loads(raw) if raw.strip() else {}
            if isinstance(data, dict):
                state_obj["events"] = data
        except Exception as e:
            print(f"[Calendar] ошибка загрузки: {e}")
            state_obj["events"] = {}

    def save_events():
        vfs = _get_vfs(root)
        if vfs is None:
            return
        try:
            vfs.write_text(EVENTS_PATH,
                           json.dumps(state_obj["events"], ensure_ascii=False, indent=2))
        except Exception as e:
            print(f"[Calendar] ошибка сохранения: {e}")

    # ---- Рендер календаря ----

    def rebuild_grid():
        # очистка
        while grid.count():
            it = grid.takeAt(0)
            w = it.widget()
            if w:
                w.setParent(None)

        year = state_obj["view_year"]
        month = state_obj["view_month"]

        month_lbl.setText(f"{MONTHS_RU[month - 1]} {year}")

        first = QDate(year, month, 1)
        # день недели 1..7 (Пн=1)
        start_col = first.dayOfWeek() - 1
        days_in_month = first.daysInMonth()

        # предыдущий месяц — заполнить пустыми
        row = 0
        col = start_col

        # Ячейки предыдущего месяца — серые пустышки
        prev_month = first.addDays(-1)
        prev_days = prev_month.day()
        for i in range(start_col):
            day_num = prev_days - start_col + i + 1
            b = QPushButton(str(day_num))
            b.setEnabled(False)
            b.setFixedHeight(56)
            b.setStyleSheet("""
                QPushButton {
                    background: rgba(255,255,255,0.02);
                    color: rgba(255,255,255,0.20);
                    border: 1px solid rgba(255,255,255,0.04);
                    border-radius: 10px;
                    font-size: 13px;
                }
            """)
            grid.addWidget(b, row, i)

        # Дни текущего месяца
        for day in range(1, days_in_month + 1):
            d = QDate(year, month, day)
            key = d.toString("yyyy-MM-dd")
            events_count = len(state_obj["events"].get(key, []))

            btn = DayButton(d, on_click=on_day_click, events_count=events_count)

            # Активный день
            if d == state_obj["selected"]:
                btn._active = True
                btn._update_style()

            btn.clicked.connect(lambda _, dd=d: on_day_click(dd))
            grid.addWidget(btn, row, col)

            col += 1
            if col > 6:
                col = 0
                row += 1

        # Заполняем последний ряд до конца (серые следующего месяца)
        if col > 0:
            for i in range(col, 7):
                b = QPushButton(str(i - col + 1))
                b.setEnabled(False)
                b.setFixedHeight(56)
                b.setStyleSheet("""
                    QPushButton {
                        background: rgba(255,255,255,0.02);
                        color: rgba(255,255,255,0.20);
                        border: 1px solid rgba(255,255,255,0.04);
                        border-radius: 10px;
                        font-size: 13px;
                    }
                """)
                grid.addWidget(b, row, i)

        # выравнивание — растянуть строки
        for r in range(grid.rowCount()):
            grid.setRowStretch(r, 1)
        for c in range(7):
            grid.setColumnStretch(c, 1)

    # ---- Выбор дня ----

    def on_day_click(date: QDate):
        state_obj["selected"] = date
        # обновить подсветку без полной перестройки
        for i in range(grid.count()):
            w = grid.itemAt(i).widget()
            if isinstance(w, DayButton):
                w._active = (w.date == date)
                w._update_style()
        render_events()

    def render_events():
        d = state_obj["selected"]
        days = ["понедельник", "вторник", "среда", "четверг",
                "пятница", "суббота", "воскресенье"]
        selected_lbl.setText(
            f"{days[d.dayOfWeek() - 1]}, {d.day()} {MONTHS_RU[d.month() - 1].lower()} {d.year()}")

        events_list.clear()
        key = d.toString("yyyy-MM-dd")
        for idx, ev in enumerate(state_obj["events"].get(key, [])):
            item = QListWidgetItem(
                f"🕐  {ev.get('time', '--:--')}    {ev.get('text', '')}")
            item.setData(Qt.UserRole, idx)
            events_list.addItem(item)

    # ---- Добавление / удаление событий ----

    def add_event():
        text = text_edit.text().strip()
        if not text:
            QMessageBox.information(root, "Календарь", "Введи текст события.")
            return
        d = state_obj["selected"]
        key = d.toString("yyyy-MM-dd")
        time_str = time_edit.time().toString("HH:mm")

        lst = state_obj["events"].setdefault(key, [])
        lst.append({"time": time_str, "text": text})
        lst.sort(key=lambda e: e["time"])

        text_edit.clear()
        save_events()
        rebuild_grid()
        render_events()

        d_obj = _get_desktop(root)
        if d_obj:
            d_obj.notifications.push("Событие добавлено",
                                     f"{time_str} — {text}")

    def delete_event():
        item = events_list.currentItem()
        if item is None:
            return
        idx = int(item.data(Qt.UserRole))
        d = state_obj["selected"]
        key = d.toString("yyyy-MM-dd")
        lst = state_obj["events"].get(key, [])
        if 0 <= idx < len(lst):
            del lst[idx]
            if not lst:
                del state_obj["events"][key]
            save_events()
            rebuild_grid()
            render_events()

    add_btn.clicked.connect(add_event)
    text_edit.returnPressed.connect(add_event)
    del_btn.clicked.connect(delete_event)

    # ---- Навигация ----

    def go_prev_month():
        m = state_obj["view_month"] - 1
        y = state_obj["view_year"]
        if m < 1:
            m = 12
            y -= 1
        state_obj["view_month"] = m
        state_obj["view_year"] = y
        rebuild_grid()

    def go_next_month():
        m = state_obj["view_month"] + 1
        y = state_obj["view_year"]
        if m > 12:
            m = 1
            y += 1
        state_obj["view_month"] = m
        state_obj["view_year"] = y
        rebuild_grid()

    def go_prev_year():
        state_obj["view_year"] -= 1
        rebuild_grid()

    def go_next_year():
        state_obj["view_year"] += 1
        rebuild_grid()

    def go_today():
        today = QDate.currentDate()
        state_obj["view_year"] = today.year()
        state_obj["view_month"] = today.month()
        state_obj["selected"] = today
        rebuild_grid()
        render_events()

    prev_month.clicked.connect(go_prev_month)
    next_month.clicked.connect(go_next_month)
    prev_year.clicked.connect(go_prev_year)
    next_year.clicked.connect(go_next_year)
    today_btn.clicked.connect(go_today)

    # ---- Старт ----
    load_events()
    rebuild_grid()
    render_events()

    return root


def _icon_btn_style():
    return """
        QPushButton {
            background: rgba(255,255,255,0.06);
            color: white;
            border: 1px solid rgba(255,255,255,0.10);
            border-radius: 8px;
            font-size: 14px;
        }
        QPushButton:hover {
            background: rgba(255,255,255,0.20);
            border: 1px solid rgba(255,255,255,0.24);
        }
        QPushButton:pressed { background: rgba(110,198,255,0.35); }
    """