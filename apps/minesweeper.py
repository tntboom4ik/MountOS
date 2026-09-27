"""
MountOS — Сапёр.

Полная реализация классической игры:
  • 3 уровня сложности: Новичок / Любитель / Профи
  • Левый клик — открыть клетку
  • Правый клик — поставить флажок
  • Двойной клик — открыть все соседние (если рядом нужное число флажков)
  • Таймер и счётчик мин
  • Рекорды по каждому уровню (в VFS)
  • Красивая отрисовка QPainter
  • Первый клик никогда не попадает на мину

Установка: apps/minesweeper.py + перезапуск MountOS.
"""

import json
import random
import time

from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QComboBox, QSizePolicy, QMessageBox
from PySide6.QtCore import Qt, QTimer, QRectF, QPointF, QPoint
from PySide6.QtGui import (QPainter, QColor, QPen, QBrush, QFont,
                            QPainterPath, QLinearGradient)

from ui.icons import get_icon
from ui.settings_state import state

APP_NAME = "Сапёр"
APP_ICON = "grid"
APP_VERSION = "1.0"
APP_AUTHOR = "MountOS"


RECORDS_PATH = "/Documents/minesweeper_records.json"


# ============================================================
#  Уровни сложности
# ============================================================

LEVELS = {
    "easy": {
        "name": "Новичок",
        "rows": 9, "cols": 9, "mines": 10,
        "cell": 34,
    },
    "medium": {
        "name": "Любитель",
        "rows": 16, "cols": 16, "mines": 40,
        "cell": 30,
    },
    "hard": {
        "name": "Профи",
        "rows": 16, "cols": 30, "mines": 99,
        "cell": 26,
    },
}


# Цифры → цвета
NUMBER_COLORS = {
    1: "#6EC6FF",
    2: "#6EE7B7",
    3: "#FF6B8A",
    4: "#B388FF",
    5: "#FFB86C",
    6: "#5EEAD4",
    7: "#F472B6",
    8: "#FBBF24",
}


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
#  Логика поля
# ============================================================

class MinesweeperBoard:
    """Логика без UI."""

    def __init__(self, rows: int, cols: int, mines: int):
        self.rows = rows
        self.cols = cols
        self.mines_total = mines

        self.mines = set()             # set((r, c))
        self.revealed = set()          # set((r, c))
        self.flagged = set()           # set((r, c))
        self.neighbors = {}            # (r, c) -> int (0-8)

        self.game_over = False
        self.won = False
        self.first_click_done = False

    def _init_mines(self, safe_r: int, safe_c: int):
        """Размещает мины, исключая первую клетку и её соседей."""
        forbidden = {(safe_r, safe_c)}
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                forbidden.add((safe_r + dr, safe_c + dc))

        candidates = [
            (r, c) for r in range(self.rows) for c in range(self.cols)
            if (r, c) not in forbidden
        ]
        # На сложных уровнях может не хватить клеток — ослабляем правило
        if len(candidates) < self.mines_total:
            candidates = [
                (r, c) for r in range(self.rows) for c in range(self.cols)
                if (r, c) != (safe_r, safe_c)
            ]

        self.mines = set(random.sample(candidates, self.mines_total))
        self._compute_neighbors()

    def _compute_neighbors(self):
        self.neighbors.clear()
        for r in range(self.rows):
            for c in range(self.cols):
                if (r, c) in self.mines:
                    continue
                count = 0
                for dr in (-1, 0, 1):
                    for dc in (-1, 0, 1):
                        if dr == 0 and dc == 0:
                            continue
                        if (r + dr, c + dc) in self.mines:
                            count += 1
                self.neighbors[(r, c)] = count

    def reveal(self, r: int, c: int) -> bool:
        """
        Открывает клетку. Возвращает True если ход успешен (не мина).
        """
        if self.game_over or (r, c) in self.revealed or (r, c) in self.flagged:
            return True
        if not (0 <= r < self.rows and 0 <= c < self.cols):
            return True

        if not self.first_click_done:
            self._init_mines(r, c)
            self.first_click_done = True

        if (r, c) in self.mines:
            # Попал на мину
            self.revealed.add((r, c))
            self.game_over = True
            return False

        # BFS-открытие пустых
        self._flood_fill(r, c)
        self._check_win()
        return True

    def _flood_fill(self, r: int, c: int):
        stack = [(r, c)]
        visited = set()
        while stack:
            cr, cc = stack.pop()
            if (cr, cc) in visited:
                continue
            visited.add((cr, cc))
            if (cr, cc) in self.mines:
                continue
            if (cr, cc) in self.flagged:
                continue
            self.revealed.add((cr, cc))

            if self.neighbors.get((cr, cc), 0) == 0:
                for dr in (-1, 0, 1):
                    for dc in (-1, 0, 1):
                        if dr == 0 and dc == 0:
                            continue
                        nr, nc = cr + dr, cc + dc
                        if 0 <= nr < self.rows and 0 <= nc < self.cols:
                            if (nr, nc) not in self.revealed:
                                stack.append((nr, nc))

    def toggle_flag(self, r: int, c: int):
        if self.game_over or (r, c) in self.revealed:
            return
        if (r, c) in self.flagged:
            self.flagged.remove((r, c))
        else:
            self.flagged.add((r, c))

    def chord(self, r: int, c: int) -> bool:
        """
        Открывает всех соседей, если флажков рядом == число.
        Возвращает False если попал на мину.
        """
        if (r, c) not in self.revealed:
            return True
        num = self.neighbors.get((r, c), 0)
        if num == 0:
            return True

        flags_around = 0
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == 0 and dc == 0:
                    continue
                if (r + dr, c + dc) in self.flagged:
                    flags_around += 1

        if flags_around != num:
            return True

        # Открываем всех незафлагованных соседей
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == 0 and dc == 0:
                    continue
                nr, nc = r + dr, c + dc
                if 0 <= nr < self.rows and 0 <= nc < self.cols:
                    if (nr, nc) not in self.revealed and (nr, nc) not in self.flagged:
                        if not self.reveal(nr, nc):
                            return False
        return True

    def _check_win(self):
        """Проверяет, что все безопасные клетки открыты."""
        safe_cells = self.rows * self.cols - self.mines_total
        if len(self.revealed) >= safe_cells:
            self.won = True
            self.game_over = True

    def flags_used(self) -> int:
        return len(self.flagged)

    def mines_left(self) -> int:
        return self.mines_total - len(self.flagged)

    def reveal_all_mines(self):
        """При проигрыше — открыть все мины."""
        self.revealed |= self.mines


# ============================================================
#  Виджет поля
# ============================================================

class MinesweeperWidget(QWidget):
    """Отрисовка поля и обработка мыши."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.StrongFocus)
        self.board = None
        self.cell_size = 30
        self.level_key = "easy"
        self._on_update = None
        self._on_win = None
        self._on_lose = None
        self._on_first_move = None

        # Для анимации нажатий
        self._pressed = None

    def set_callbacks(self, on_update=None, on_win=None,
                       on_lose=None, on_first_move=None):
        self._on_update = on_update
        self._on_win = on_win
        self._on_lose = on_lose
        self._on_first_move = on_first_move

    def new_game(self, level_key: str = None):
        if level_key:
            self.level_key = level_key
        level = LEVELS[self.level_key]
        self.cell_size = level["cell"]
        self.board = MinesweeperBoard(level["rows"], level["cols"], level["mines"])
        self._pressed = None
        self.setFixedSize(
            self.board.cols * self.cell_size,
            self.board.rows * self.cell_size,
        )
        self.update()
        if self._on_update:
            self._on_update()

    # ------------------------------------------------------------
    #  Мышь
    # ------------------------------------------------------------

    def _cell_at(self, pos: QPoint) -> tuple:
        c = pos.x() // self.cell_size
        r = pos.y() // self.cell_size
        if 0 <= r < self.board.rows and 0 <= c < self.board.cols:
            return (r, c)
        return None

    def mousePressEvent(self, e):
        if not self.board or self.board.game_over:
            return
        cell = self._cell_at(e.position().toPoint())
        if cell is None:
            return
        r, c = cell

        if e.button() == Qt.LeftButton:
            if (r, c) not in self.board.revealed:
                self._pressed = (r, c)
                self.update()

    def mouseReleaseEvent(self, e):
        if not self.board or self.board.game_over:
            return
        cell = self._cell_at(e.position().toPoint())
        self._pressed = None

        if cell is None:
            self.update()
            return
        r, c = cell

        if e.button() == Qt.LeftButton:
            was_first = not self.board.first_click_done
            ok = self.board.reveal(r, c)
            if was_first and self._on_first_move:
                self._on_first_move()
            self.update()
            if self._on_update:
                self._on_update()
            if not ok:
                self.board.reveal_all_mines()
                self.update()
                if self._on_lose:
                    self._on_lose()
            elif self.board.won:
                if self._on_win:
                    self._on_win()

        elif e.button() == Qt.RightButton:
            self.board.toggle_flag(r, c)
            self.update()
            if self._on_update:
                self._on_update()

        elif e.button() == Qt.MiddleButton:
            # Средняя кнопка — chord
            ok = self.board.chord(r, c)
            self.update()
            if self._on_update:
                self._on_update()
            if not ok:
                self.board.reveal_all_mines()
                self.update()
                if self._on_lose:
                    self._on_lose()
            elif self.board.won:
                if self._on_win:
                    self._on_win()

    def mouseDoubleClickEvent(self, e):
        """Двойной левый клик — chord (как в настоящем сапёре)."""
        if not self.board or self.board.game_over:
            return
        cell = self._cell_at(e.position().toPoint())
        if cell is None:
            return
        r, c = cell
        if e.button() == Qt.LeftButton:
            if (r, c) in self.board.revealed:
                ok = self.board.chord(r, c)
                self.update()
                if self._on_update:
                    self._on_update()
                if not ok:
                    self.board.reveal_all_mines()
                    self.update()
                    if self._on_lose:
                        self._on_lose()
                elif self.board.won:
                    if self._on_win:
                        self._on_win()

    # ------------------------------------------------------------
    #  Отрисовка
    # ------------------------------------------------------------

    def paintEvent(self, event):
        if not self.board:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        cs = self.cell_size
        for r in range(self.board.rows):
            for c in range(self.board.cols):
                self._draw_cell(p, r, c, cs)

    def _draw_cell(self, p: QPainter, r: int, c: int, cs: int):
        x = c * cs
        y = r * cs
        rect = QRectF(x + 1, y + 1, cs - 2, cs - 2)

        revealed = (r, c) in self.board.revealed
        flagged = (r, c) in self.board.flagged
        is_mine = (r, c) in self.board.mines
        pressed = self._pressed == (r, c)

        if revealed:
            if is_mine:
                # Красный фон для мины
                bg = QColor("#7F1D1D")
            else:
                bg = QColor("#1E2438")
        else:
            # Накрытая клетка
            if pressed:
                bg = QColor("#2A3149")
            else:
                bg = QColor("#3A4160")

        p.setBrush(QBrush(bg))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(rect, 4, 4)

        # Внутренняя подсветка (эффект кнопки)
        if not revealed:
            highlight = QColor(255, 255, 255, 30)
            p.setBrush(QBrush(highlight))
            top = QRectF(rect.left(), rect.top(), rect.width(), 2)
            p.drawRoundedRect(top, 2, 2)

        # Флажок
        if flagged and not revealed:
            self._draw_flag(p, rect)
            return

        # Раскрытая клетка
        if revealed:
            if is_mine:
                self._draw_mine(p, rect)
            else:
                num = self.board.neighbors.get((r, c), 0)
                if num > 0:
                    self._draw_number(p, rect, num)

    def _draw_number(self, p: QPainter, rect: QRectF, num: int):
        color = QColor(NUMBER_COLORS.get(num, "#FFFFFF"))
        p.setPen(color)
        font = QFont()
        font.setPointSize(int(self.cell_size * 0.5))
        font.setBold(True)
        p.setFont(font)
        p.drawText(rect, Qt.AlignCenter, str(num))

    def _draw_mine(self, p: QPainter, rect: QRectF):
        cx = rect.center().x()
        cy = rect.center().y()
        rad = rect.width() * 0.30

        # Основной круг
        p.setBrush(QBrush(QColor("#0A0E1A")))
        p.setPen(QPen(QColor("#1A1F35"), 2))
        p.drawEllipse(QPointF(cx, cy), rad, rad)

        # Лучи
        p.setPen(QPen(QColor("#0A0E1A"), 2))
        for angle in range(0, 360, 45):
            import math
            ar = math.radians(angle)
            x1 = cx + math.cos(ar) * rad * 0.7
            y1 = cy + math.sin(ar) * rad * 0.7
            x2 = cx + math.cos(ar) * rad * 1.4
            y2 = cy + math.sin(ar) * rad * 1.4
            p.drawLine(QPointF(x1, y1), QPointF(x2, y2))

        # Блик
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor(255, 255, 255, 180)))
        p.drawEllipse(QPointF(cx - rad * 0.3, cy - rad * 0.3),
                       rad * 0.25, rad * 0.25)

    def _draw_flag(self, p: QPainter, rect: QRectF):
        cx = rect.center().x()
        cy = rect.center().y()
        size = rect.width()

        # Флажок — красный треугольник
        flag_path = QPainterPath()
        flag_path.moveTo(cx - size * 0.05, cy - size * 0.30)
        flag_path.lineTo(cx + size * 0.30, cy - size * 0.10)
        flag_path.lineTo(cx - size * 0.05, cy + size * 0.10)
        flag_path.closeSubpath()

        p.setBrush(QBrush(QColor("#FF6B8A")))
        p.setPen(Qt.NoPen)
        p.drawPath(flag_path)

        # Древко
        p.setPen(QPen(QColor("#1A1F35"), 2))
        p.drawLine(QPointF(cx - size * 0.05, cy - size * 0.35),
                   QPointF(cx - size * 0.05, cy + size * 0.30))

        # База
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor("#1A1F35")))
        p.drawRoundedRect(
            QRectF(cx - size * 0.25, cy + size * 0.25,
                   size * 0.40, size * 0.08), 1, 1)


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
        "start_time": 0.0,
        "timer_running": False,
        "records": {},       # {"easy": seconds, "medium": ..., "hard": ...}
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

    # ---- Левая панель — поле ----
    left = QWidget()
    ll = QVBoxLayout(left)
    ll.setContentsMargins(30, 30, 30, 30)
    ll.setSpacing(16)
    ll.setAlignment(Qt.AlignCenter)

    board = MinesweeperWidget()
    board.new_game("easy")
    ll.addWidget(board, 0, Qt.AlignCenter)

    hint = QLabel("ЛКМ — открыть · ПКМ — флажок · Двойной ЛКМ — открыть соседей")
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

    title = QLabel("💣  Сапёр")
    title.setStyleSheet("color: white; font-size: 20px; font-weight: 600; padding: 2px;")
    rl.addWidget(title)

    hint2 = QLabel("Открой все клетки без мин.\nЧисло = количество мин рядом.")
    hint2.setStyleSheet("color: rgba(255,255,255,0.55); font-size: 12px;")
    hint2.setWordWrap(True)
    rl.addWidget(hint2)

    rl.addSpacing(10)

    # ---- Уровень сложности ----
    level_lbl = QLabel("УРОВЕНЬ")
    level_lbl.setStyleSheet("""
        color: rgba(255,255,255,0.45);
        font-size: 10px;
        font-weight: 700;
        letter-spacing: 1.5px;
    """)
    rl.addWidget(level_lbl)

    level_combo = QComboBox()
    for key, data in LEVELS.items():
        level_combo.addItem(f"{data['name']}  ({data['mines']} мин)", key)
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

    # ---- Метрики ----
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

    mines_box, mines_val = make_metric("МИН ОСТАЛОСЬ", "grid", "255,107,138")
    rl.addWidget(mines_box)

    time_box, time_val = make_metric("ВРЕМЯ", "clock", "110,198,255")
    rl.addWidget(time_box)

    rl.addSpacing(10)

    # ---- Рекорды ----
    rec_lbl = QLabel("РЕКОРДЫ")
    rec_lbl.setStyleSheet(level_lbl.styleSheet())
    rl.addWidget(rec_lbl)

    records_widget = QWidget()
    records_widget.setStyleSheet("""
        QWidget {
            background: rgba(255,184,108,0.10);
            border: 1px solid rgba(255,184,108,0.30);
            border-radius: 12px;
        }
    """)
    rwl = QVBoxLayout(records_widget)
    rwl.setContentsMargins(14, 10, 14, 10)
    rwl.setSpacing(4)

    record_labels = {}
    for key, data in LEVELS.items():
        row = QHBoxLayout()
        name_lbl = QLabel(data["name"])
        name_lbl.setStyleSheet("""
            color: rgba(255,255,255,0.65);
            font-size: 11px;
            background: transparent;
            border: none;
        """)
        row.addWidget(name_lbl)
        row.addStretch(1)
        time_lbl = QLabel("—")
        time_lbl.setStyleSheet("""
            color: #FFB86C;
            font-size: 12px;
            font-weight: 600;
            background: transparent;
            border: none;
        """)
        row.addWidget(time_lbl)
        record_labels[key] = time_lbl
        rwl.addLayout(row)

    rl.addWidget(records_widget)

    rl.addStretch(1)

    # ---- Кнопки ----
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
            sec = st["records"].get(key)
            if sec:
                m = sec // 60
                s = sec % 60
                lbl.setText(f"{m:02d}:{s:02d}")
            else:
                lbl.setText("—")

    def update_ui():
        if not board.board:
            return
        mines_val.setText(str(board.board.mines_left()))
        if st["timer_running"]:
            elapsed = int(time.time() - st["start_time"])
            m = elapsed // 60
            s = elapsed % 60
            time_val.setText(f"{m:02d}:{s:02d}")
        else:
            time_val.setText("00:00")

    def on_first_move():
        st["start_time"] = time.time()
        st["timer_running"] = True
        timer.start()

    def on_tick():
        if st["timer_running"]:
            update_ui()

    timer.timeout.connect(on_tick)

    def on_win():
        timer.stop()
        st["timer_running"] = False
        elapsed = int(time.time() - st["start_time"])
        m = elapsed // 60
        s = elapsed % 60

        # Обновляем рекорд
        key = board.level_key
        cur = st["records"].get(key)
        new_record = (cur is None or elapsed < cur)
        if new_record:
            st["records"][key] = elapsed
            save_records()
            update_records_ui()

        # Уведомление
        if desktop and hasattr(desktop, "notifications"):
            desktop.notifications.push(
                "🏆 Победа!",
                f"{LEVELS[key]['name']}: {m:02d}:{s:02d}"
                + ("  (новый рекорд!)" if new_record else ""))

        QMessageBox.information(
            root, "🏆 Победа!",
            f"Ты разминировал поле!\n\n"
            f"Время: {m:02d}:{s:02d}\n"
            f"{'🏆 Новый рекорд!' if new_record else ''}")

    def on_lose():
        timer.stop()
        st["timer_running"] = False
        if desktop and hasattr(desktop, "notifications"):
            desktop.notifications.push("💥 Бум!", "Ты наступил на мину")

    board.set_callbacks(
        on_update=update_ui,
        on_win=on_win,
        on_lose=on_lose,
        on_first_move=on_first_move,
    )

    def new_game():
        timer.stop()
        st["timer_running"] = False
        st["start_time"] = 0
        key = level_combo.currentData()
        board.new_game(key)
        update_ui()
        time_val.setText("00:00")

    new_btn.clicked.connect(new_game)
    level_combo.currentIndexChanged.connect(new_game)

    # Стартовая загрузка
    update_records_ui()
    update_ui()
    QTimer.singleShot(200, board.setFocus)

    return root