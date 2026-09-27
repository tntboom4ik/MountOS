"""
MountOS — Memory.

Игра «Найди пары»:
  • Сетки 4×4, 4×6, 6×6 (Легко / Средне / Сложно)
  • 8 / 12 / 18 пар эмодзи-иконок
  • Плавный переворот карточек (анимация)
  • Счётчик ходов и времени
  • Рекорды по каждому уровню (в VFS)
  • Автосохранение прогресса
  • Красивая отрисовка QPainter

Установка: apps/memory.py + перезапуск MountOS.
"""

import json
import random
import time

from PySide6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QLabel,
                                QPushButton, QComboBox, QMessageBox)
from PySide6.QtCore import (Qt, QTimer, QRectF, QPointF, QPropertyAnimation,
                             QEasingCurve, Signal, QObject)
from PySide6.QtGui import (QPainter, QColor, QPen, QBrush, QFont,
                            QPainterPath, QLinearGradient)

from ui.icons import get_icon
from ui.settings_state import state

APP_NAME = "Memory"
APP_ICON = "grid"
APP_VERSION = "1.0"
APP_AUTHOR = "MountOS"


SAVE_PATH = "/Documents/memory_save.json"
RECORDS_PATH = "/Documents/memory_records.json"


# ============================================================
#  Уровни
# ============================================================

LEVELS = {
    "easy":   {"name": "Легко",   "cols": 4, "rows": 4, "cell": 110},
    "medium": {"name": "Средне",  "cols": 6, "rows": 4, "cell": 100},
    "hard":   {"name": "Сложно",  "cols": 6, "rows": 6, "cell": 90},
}


# Эмодзи-наборы — 18 штук (максимум для 6×6)
SYMBOLS = [
    "🍎", "🍌", "🍇", "🍓", "🍒", "🍑",
    "🐶", "🐱", "🐭", "🐰", "🦊", "🐻",
    "⭐", "🌙", "☀️", "⚡", "💧", "🔥",
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
#  Карточка
# ============================================================

class Card:
    """Модель одной карточки."""

    def __init__(self, symbol: str):
        self.symbol = symbol
        self.matched = False
        self.flip_progress = 0.0   # 0..1 — анимация переворота
        self.target_flip = 0.0     # куда идём (0 или 1)

    def is_face_up(self) -> bool:
        return self.flip_progress > 0.5

    def start_flip(self, to_face_up: bool):
        self.target_flip = 1.0 if to_face_up else 0.0

    def tick(self, dt: float) -> bool:
        """Обновляет анимацию переворота. Возвращает True если ещё анимируется."""
        if abs(self.flip_progress - self.target_flip) < 0.01:
            self.flip_progress = self.target_flip
            return False
        diff = self.target_flip - self.flip_progress
        step = 0.15
        if abs(diff) < step:
            self.flip_progress = self.target_flip
        else:
            self.flip_progress += step if diff > 0 else -step
        return True


# ============================================================
#  Игровое поле
# ============================================================

class MemoryWidget(QWidget):
    """Отрисовка поля Memory и логика переворотов."""

    game_finished = Signal(int, int)   # moves, seconds
    moves_changed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.StrongFocus)

        self.cols = 4
        self.rows = 4
        self.cell = 110
        self.gap = 10

        self.cards = []       # список Card
        self.first_pick = None
        self.second_pick = None
        self.moves = 0
        self.locked = False   # блокировка ввода пока идёт анимация
        self.game_active = False

        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(16)
        self._anim_timer.timeout.connect(self._anim_tick)

        self._flip_delay = QTimer(self)
        self._flip_delay.setSingleShot(True)
        self._flip_delay.timeout.connect(self._resolve_pair)

    # ------------------------------------------------------------

    def new_game(self, level_key: str):
        level = LEVELS[level_key]
        self.cols = level["cols"]
        self.rows = level["rows"]
        self.cell = level["cell"]

        # Сколько пар
        total_cards = self.cols * self.rows
        pairs = total_cards // 2
        symbols = SYMBOLS[:pairs] * 2
        random.shuffle(symbols)

        self.cards = [Card(s) for s in symbols]
        self.first_pick = None
        self.second_pick = None
        self.moves = 0
        self.locked = False
        self.game_active = True

        self.setFixedSize(
            self.cols * self.cell + (self.cols + 1) * self.gap,
            self.rows * self.cell + (self.rows + 1) * self.gap,
        )

        # Все карточки — рубашкой вверх
        for c in self.cards:
            c.flip_progress = 0.0
            c.target_flip = 0.0

        self._anim_timer.start()
        self.update()
        self.moves_changed.emit(0)

    def set_data(self, data: dict):
        """Восстанавливает игру из сохранения."""
        self.cols = data.get("cols", 4)
        self.rows = data.get("rows", 4)
        self.cell = data.get("cell", 110)
        symbols = data.get("symbols", [])
        matched = data.get("matched", [])
        self.moves = data.get("moves", 0)
        self.game_active = data.get("active", True)

        self.cards = []
        for i, sym in enumerate(symbols):
            card = Card(sym)
            card.matched = matched[i] if i < len(matched) else False
            # Совпавшие — сразу открыты
            if card.matched:
                card.flip_progress = 1.0
                card.target_flip = 1.0
            self.cards.append(card)

        self.setFixedSize(
            self.cols * self.cell + (self.cols + 1) * self.gap,
            self.rows * self.cell + (self.rows + 1) * self.gap,
        )

        self._anim_timer.start()
        self.update()
        self.moves_changed.emit(self.moves)

    def get_data(self) -> dict:
        return {
            "cols": self.cols,
            "rows": self.rows,
            "cell": self.cell,
            "symbols": [c.symbol for c in self.cards],
            "matched": [c.matched for c in self.cards],
            "moves": self.moves,
            "active": self.game_active,
        }

    def is_complete(self) -> bool:
        return all(c.matched for c in self.cards)

    # ------------------------------------------------------------

    def _index_at(self, pos: QPointF) -> int:
        """Возвращает индекс карточки по координатам, или -1."""
        x = pos.x()
        y = pos.y()
        c = int(x // (self.cell + self.gap))
        r = int(y // (self.cell + self.gap))
        if not (0 <= r < self.rows and 0 <= c < self.cols):
            return -1
        # Точная проверка внутри карточки
        cx = c * (self.cell + self.gap) + self.gap
        cy = r * (self.cell + self.gap) + self.gap
        if cx <= x <= cx + self.cell and cy <= y <= cy + self.cell:
            return r * self.cols + c
        return -1

    def mousePressEvent(self, e):
        if not self.game_active or self.locked:
            return
        if e.button() != Qt.LeftButton:
            return
        idx = self._index_at(e.position())
        if idx < 0:
            return
        card = self.cards[idx]
        if card.matched:
            return
        if card.is_face_up():
            return
        if idx == self.first_pick:
            return

        # Переворачиваем
        card.start_flip(True)
        self._anim_timer.start()

        if self.first_pick is None:
            self.first_pick = idx
        elif self.second_pick is None:
            self.second_pick = idx
            self.moves += 1
            self.moves_changed.emit(self.moves)
            self.locked = True
            # Дадим 700 мс на просмотр, потом решаем
            self._flip_delay.start(700)

    def _resolve_pair(self):
        if self.first_pick is None or self.second_pick is None:
            self.locked = False
            return
        a = self.cards[self.first_pick]
        b = self.cards[self.second_pick]
        if a.symbol == b.symbol:
            a.matched = True
            b.matched = True
            self.first_pick = None
            self.second_pick = None
            self.locked = False
            self._anim_timer.start()
            self.update()
            if self.is_complete():
                self.game_active = False
                # Уведомляем через сигнал
                self.game_finished.emit(self.moves, 0)
        else:
            # Переворачиваем обратно
            a.start_flip(False)
            b.start_flip(False)
            self.first_pick = None
            self.second_pick = None
            self.locked = False
            self._anim_timer.start()
            self.update()

    def _anim_tick(self):
        any_active = False
        for c in self.cards:
            if c.tick(0):
                any_active = True
        self.update()
        if not any_active and not self.locked:
            self._anim_timer.stop()

    # ------------------------------------------------------------

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        accent = state().get("accent", "#6EC6FF")

        # Фон
        p.fillRect(self.rect(), QColor("#0E1420"))

        for i, card in enumerate(self.cards):
            r = i // self.cols
            c = i % self.cols
            x = c * (self.cell + self.gap) + self.gap
            y = r * (self.cell + self.gap) + self.gap
            self._draw_card(p, card, x, y, accent)

    def _draw_card(self, p: QPainter, card: Card, x: float, y: float, accent: str):
        rect = QRectF(x, y, self.cell, self.cell)

        # Анимация переворота через масштаб по горизонтали
        progress = card.flip_progress
        scale_x = abs(1 - 2 * progress)   # 1 → 0 → 1
        if scale_x < 0.02:
            scale_x = 0.02
        cx = rect.center().x()
        w = rect.width() * scale_x
        visible_rect = QRectF(cx - w / 2, rect.top(), w, rect.height())

        # Что показываем — рубашку или лицо?
        show_face = progress > 0.5

        if show_face:
            # Лицо карточки
            if card.matched:
                # Совпавшая — приглушённая
                bg1 = QColor(30, 40, 60, 200)
                bg2 = QColor(20, 28, 44, 200)
                border = QColor(accent)
                border.setAlpha(150)
            else:
                bg1 = QColor(40, 48, 70)
                bg2 = QColor(30, 36, 54)
                border = QColor(accent)
                border.setAlpha(200)

            grad = QLinearGradient(0, visible_rect.top(),
                                    0, visible_rect.bottom())
            grad.setColorAt(0, bg1)
            grad.setColorAt(1, bg2)
            p.setBrush(QBrush(grad))
            p.setPen(QPen(border, 2))
            p.drawRoundedRect(visible_rect, 12, 12)

            # Символ
            if visible_rect.width() > 20:
                p.setPen(QColor(255, 255, 255))
                font = QFont()
                font.setPointSize(int(self.cell * 0.40))
                p.setFont(font)
                p.drawText(visible_rect, Qt.AlignCenter, card.symbol)

        else:
            # Рубашка
            grad = QLinearGradient(0, visible_rect.top(),
                                    0, visible_rect.bottom())
            grad.setColorAt(0, QColor(accent))
            grad.setColorAt(1, QColor(accent).darker(150))
            p.setBrush(QBrush(grad))
            p.setPen(QPen(QColor(accent).lighter(120), 2))
            p.drawRoundedRect(visible_rect, 12, 12)

            # Внутренний узор
            if visible_rect.width() > 20:
                inner = visible_rect.adjusted(
                    visible_rect.width() * 0.2,
                    visible_rect.height() * 0.2,
                    -visible_rect.width() * 0.2,
                    -visible_rect.height() * 0.2)
                p.setPen(QPen(QColor(255, 255, 255, 60), 2))
                p.setBrush(Qt.NoBrush)
                p.drawRoundedRect(inner, 6, 6)
                # Ромб
                path = QPainterPath()
                path.moveTo(inner.center().x(), inner.top())
                path.lineTo(inner.right(), inner.center().y())
                path.lineTo(inner.center().x(), inner.bottom())
                path.lineTo(inner.left(), inner.center().y())
                path.closeSubpath()
                p.setPen(QPen(QColor(255, 255, 255, 40), 2))
                p.drawPath(path)


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
        "level": "easy",
        "start_time": 0.0,
        "timer_running": False,
        "elapsed": 0,
        "records": {},
    }

    # ---- Загрузка рекордов ----
    if vfs:
        try:
            raw = vfs.read_text(RECORDS_PATH, "")
            if raw.strip():
                st["records"] = json.loads(raw)
        except Exception:
            st["records"] = {}

    def save_records():
        if vfs is None:
            return
        try:
            vfs.mkdir("/Documents")
            vfs.write_text(RECORDS_PATH,
                json.dumps(st["records"], ensure_ascii=False, indent=2))
        except Exception:
            pass

    # ---- Левая панель ----
    left = QWidget()
    ll = QVBoxLayout(left)
    ll.setContentsMargins(30, 30, 30, 30)
    ll.setSpacing(16)
    ll.setAlignment(Qt.AlignCenter)

    board = MemoryWidget()
    ll.addWidget(board, 0, Qt.AlignCenter)

    hint = QLabel("Кликни по карточке — открой её и найди пару за минимальное число ходов")
    hint.setAlignment(Qt.AlignCenter)
    hint.setStyleSheet("color: rgba(255,255,255,0.45); font-size: 11px;")
    ll.addWidget(hint)

    h.addWidget(left, 1)

    # ---- Правая панель ----
    right = QWidget()
    right.setFixedWidth(280)
    right.setStyleSheet("""
        background: rgba(255,255,255,0.04);
        border-left: 1px solid rgba(255,255,255,0.08);
    """)
    rl = QVBoxLayout(right)
    rl.setContentsMargins(20, 24, 20, 24)
    rl.setSpacing(14)

    title = QLabel("🎴  Memory")
    title.setStyleSheet("color: white; font-size: 20px; font-weight: 600; padding: 2px;")
    rl.addWidget(title)

    hint2 = QLabel("Открывай по две карточки.\nЕсли символы совпали — они остаются открытыми.")
    hint2.setStyleSheet("color: rgba(255,255,255,0.55); font-size: 12px;")
    hint2.setWordWrap(True)
    rl.addWidget(hint2)

    rl.addSpacing(10)

    # Уровень
    lvl_lbl = QLabel("УРОВЕНЬ")
    lvl_lbl.setStyleSheet("""
        color: rgba(255,255,255,0.45);
        font-size: 10px;
        font-weight: 700;
        letter-spacing: 1.5px;
    """)
    rl.addWidget(lvl_lbl)

    level_combo = QComboBox()
    for key, data in LEVELS.items():
        level_combo.addItem(f"{data['name']}  ({data['cols']}×{data['rows']})", key)
    level_combo.setStyleSheet("""
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
        }
    """)
    rl.addWidget(level_combo)

    # Метрики
    def make_metric(title_text: str, icon_name: str, color: str) -> tuple:
        box = QWidget()
        box.setStyleSheet(f"""
            QWidget {{
                background: rgba({color}, 0.12);
                border: 1px solid rgba({color}, 0.35);
                border-radius: 12px;
            }}
        """)
        bl = QHBoxLayout(box)
        bl.setContentsMargins(14, 10, 14, 10)
        bl.setSpacing(10)

        ic = QLabel()
        ic.setFixedSize(24, 24)
        ic.setPixmap(get_icon(icon_name, 18, "#FFFFFF"))
        ic.setStyleSheet("background: transparent; border: none;")
        bl.addWidget(ic)

        col = QVBoxLayout()
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(2)

        t = QLabel(title_text)
        t.setStyleSheet("""
            color: rgba(255,255,255,0.55);
            font-size: 9px;
            font-weight: 700;
            letter-spacing: 1.2px;
            background: transparent;
            border: none;
        """)
        col.addWidget(t)

        v = QLabel("0")
        v.setStyleSheet("""
            color: white;
            font-size: 20px;
            font-weight: 600;
            background: transparent;
            border: none;
        """)
        col.addWidget(v)

        bl.addLayout(col, 1)
        return box, v

    moves_box, moves_val = make_metric("ХОДОВ", "grid", "110,198,255")
    rl.addWidget(moves_box)

    time_box, time_val = make_metric("ВРЕМЯ", "clock", "255,184,108")
    rl.addWidget(time_box)

    pairs_box, pairs_val = make_metric("ПАРЫ", "star", "110,231,183")
    rl.addWidget(pairs_box)

    rl.addSpacing(10)

    # Рекорды
    rec_lbl = QLabel("РЕКОРДЫ")
    rec_lbl.setStyleSheet(lvl_lbl.styleSheet())
    rl.addWidget(rec_lbl)

    rec_box = QWidget()
    rec_box.setStyleSheet("""
        QWidget {
            background: rgba(255,184,108,0.10);
            border: 1px solid rgba(255,184,108,0.30);
            border-radius: 12px;
        }
    """)
    rbl = QVBoxLayout(rec_box)
    rbl.setContentsMargins(14, 10, 14, 10)
    rbl.setSpacing(4)

    record_labels = {}
    for key, data in LEVELS.items():
        row = QHBoxLayout()
        nm = QLabel(data["name"])
        nm.setStyleSheet("""
            color: rgba(255,255,255,0.65);
            font-size: 11px;
            background: transparent;
            border: none;
        """)
        row.addWidget(nm)
        row.addStretch(1)
        vl = QLabel("—")
        vl.setStyleSheet("""
            color: #FFB86C;
            font-size: 12px;
            font-weight: 600;
            background: transparent;
            border: none;
        """)
        row.addWidget(vl)
        record_labels[key] = vl
        rbl.addLayout(row)

    rl.addWidget(rec_box)

    rl.addStretch(1)

    # Кнопки
    new_btn = QPushButton("🔄  Новая игра")
    new_btn.setCursor(Qt.PointingHandCursor)
    new_btn.setFixedHeight(42)
    new_btn.setStyleSheet("""
        QPushButton {
            background: rgba(110,198,255,0.25);
            color: white;
            border: 1px solid rgba(110,198,255,0.60);
            border-radius: 10px;
            font-size: 13px;
            font-weight: 600;
        }
        QPushButton:hover { background: rgba(110,198,255,0.45); }
    """)
    rl.addWidget(new_btn)

    h.addWidget(right)

    # ============================================================
    #  Логика
    # ============================================================

    timer = QTimer(root)
    timer.setInterval(1000)

    def update_records_ui():
        for key, lbl in record_labels.items():
            rec = st["records"].get(key)
            if rec:
                m = rec.get("moves", 0)
                s = rec.get("time", 0)
                mm = s // 60
                ss = s % 60
                lbl.setText(f"{m} ход  ·  {mm:02d}:{ss:02d}")
            else:
                lbl.setText("—")

    def update_metrics():
        moves_val.setText(str(board.moves))
        matched = sum(1 for c in board.cards if c.matched)
        total_pairs = len(board.cards) // 2
        pairs_val.setText(f"{matched // 2} / {total_pairs}")
        if st["timer_running"]:
            st["elapsed"] = int(time.time() - st["start_time"])
            m = st["elapsed"] // 60
            s = st["elapsed"] % 60
            time_val.setText(f"{m:02d}:{s:02d}")

    def on_tick():
        if st["timer_running"]:
            update_metrics()

    timer.timeout.connect(on_tick)

    def on_moves_changed(_):
        update_metrics()

    def on_game_finished(moves, _):
        timer.stop()
        st["timer_running"] = False
        elapsed = int(time.time() - st["start_time"])

        key = st["level"]
        cur = st["records"].get(key)
        new_record = False
        if cur is None:
            new_record = True
        else:
            # Меньше ходов — лучше. При равенстве ходов — меньше времени.
            if (moves < cur["moves"]) or \
               (moves == cur["moves"] and elapsed < cur["time"]):
                new_record = True
        if new_record:
            st["records"][key] = {"moves": moves, "time": elapsed}
            save_records()
            update_records_ui()

        m = elapsed // 60
        s = elapsed % 60

        if desktop and hasattr(desktop, "notifications"):
            desktop.notifications.push(
                "🎉 Memory пройден!",
                f"{LEVELS[key]['name']}: {moves} ходов, {m:02d}:{s:02d}"
                + ("  (новый рекорд!)" if new_record else ""))

        QMessageBox.information(root, "🎉 Победа!",
            f"Ты нашёл все пары!\n\n"
            f"Ходов: {moves}\n"
            f"Время: {m:02d}:{s:02d}\n"
            f"{'🏆 Новый рекорд!' if new_record else ''}")

    board.game_finished.connect(on_game_finished)
    board.moves_changed.connect(on_moves_changed)

    def save_game():
        if vfs is None:
            return
        try:
            vfs.mkdir("/Documents")
            data = board.get_data()
            data["level"] = st["level"]
            data["elapsed"] = st["elapsed"]
            data["saved_at"] = time.time()
            vfs.write_text(SAVE_PATH,
                            json.dumps(data, ensure_ascii=False, indent=2))
        except Exception as e:
            print(f"[Memory] save: {e}")

    def load_game() -> bool:
        if vfs is None:
            return False
        try:
            raw = vfs.read_text(SAVE_PATH, "")
            if not raw.strip():
                return False
            data = json.loads(raw)
            if not data.get("active", False):
                return False
            board.set_data(data)
            st["level"] = data.get("level", "easy")
            idx = level_combo.findData(st["level"])
            if idx >= 0:
                level_combo.blockSignals(True)
                level_combo.setCurrentIndex(idx)
                level_combo.blockSignals(False)

            st["elapsed"] = data.get("elapsed", 0)
            st["start_time"] = time.time() - st["elapsed"]
            st["timer_running"] = True
            timer.start()
            update_metrics()
            return True
        except Exception as e:
            print(f"[Memory] load: {e}")
            return False

    def new_game():
        timer.stop()
        st["timer_running"] = False
        st["elapsed"] = 0

        key = level_combo.currentData()
        st["level"] = key
        board.new_game(key)

        st["start_time"] = time.time()
        st["timer_running"] = True
        timer.start()
        update_metrics()

    new_btn.clicked.connect(new_game)
    level_combo.currentIndexChanged.connect(new_game)

    # Автосохранение
    autosave = QTimer(root)
    autosave.setInterval(5000)
    autosave.timeout.connect(save_game)
    autosave.start()

    # Загрузка или новая
    if not load_game():
        new_game()
    else:
        update_metrics()

    update_records_ui()
    QTimer.singleShot(200, board.setFocus)

    return root