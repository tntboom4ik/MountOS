"""
MountOS — Судоку.

Полная реализация классической головоломки:
  • Генератор судоку (алгоритм с возвратом + удаление клеток)
  • 4 уровня сложности: Легко / Средне / Сложно / Эксперт
  • Валидация ходов в реальном времени
  • Заметки (pencil marks) — несколько цифр в клетке
  • Подсказка (заполнить одну случайную клетку)
  • Проверка решения
  • Автосохранение
  • Таймер и статистика

Установка: apps/sudoku.py + перезапуск MountOS.
"""

import json
import random
import time
import copy

from PySide6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QLabel,
                                QPushButton, QComboBox, QSizePolicy, QMessageBox,
                                QInputDialog)
from PySide6.QtCore import Qt, QTimer, QRectF, QPointF, Signal
from PySide6.QtGui import (QPainter, QColor, QPen, QBrush, QFont,
                            QPainterPath)

from ui.icons import get_icon
from ui.settings_state import state

APP_NAME = "Судоку"
APP_ICON = "grid"
APP_VERSION = "1.0"
APP_AUTHOR = "MountOS"


SAVE_PATH = "/Documents/sudoku_save.json"
STATS_PATH = "/Documents/sudoku_stats.json"

GRID = 9
CELL_SIZE = 60


# ============================================================
#  Уровни сложности
# ============================================================

DIFFICULTY = {
    "easy":    {"name": "Легко",   "remove": 35},
    "medium":  {"name": "Средне",  "remove": 45},
    "hard":    {"name": "Сложно",  "remove": 52},
    "expert":  {"name": "Эксперт", "remove": 58},
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
#  Генератор / решатель судоку
# ============================================================

def is_valid(board: list, r: int, c: int, val: int) -> bool:
    """Проверяет, можно ли поставить val в (r, c) без конфликтов."""
    for i in range(GRID):
        if board[r][i] == val and i != c:
            return False
        if board[i][c] == val and i != r:
            return False
    br = (r // 3) * 3
    bc = (c // 3) * 3
    for i in range(br, br + 3):
        for j in range(bc, bc + 3):
            if board[i][j] == val and (i != r or j != c):
                return False
    return True


def solve_board(board: list) -> bool:
    """Решает судоку in-place. True если решено."""
    for r in range(GRID):
        for c in range(GRID):
            if board[r][c] == 0:
                nums = list(range(1, 10))
                random.shuffle(nums)
                for n in nums:
                    if is_valid(board, r, c, n):
                        board[r][c] = n
                        if solve_board(board):
                            return True
                        board[r][c] = 0
                return False
    return True


def count_solutions(board: list, limit: int = 2) -> int:
    """Считает число решений (до limit)."""
    for r in range(GRID):
        for c in range(GRID):
            if board[r][c] == 0:
                count = 0
                for n in range(1, 10):
                    if is_valid(board, r, c, n):
                        board[r][c] = n
                        count += count_solutions(board, limit - count)
                        board[r][c] = 0
                        if count >= limit:
                            return count
                return count
    return 1


def generate_sudoku(difficulty_key: str = "medium") -> tuple:
    """
    Генерирует новую судоку.
    Возвращает (puzzle, solution) — обе матрицы 9×9.
    """
    remove_count = DIFFICULTY[difficulty_key]["remove"]

    # 1. Создаём полное решённое поле
    solved = [[0] * GRID for _ in range(GRID)]
    solve_board(solved)

    puzzle = [row[:] for row in solved]

    # 2. Убираем числа в случайном порядке
    cells = [(r, c) for r in range(GRID) for c in range(GRID)]
    random.shuffle(cells)

    removed = 0
    for r, c in cells:
        if removed >= remove_count:
            break
        backup = puzzle[r][c]
        if backup == 0:
            continue
        puzzle[r][c] = 0
        # Проверяем, что решение единственное
        test = [row[:] for row in puzzle]
        if count_solutions(test, limit=2) != 1:
            puzzle[r][c] = backup
        else:
            removed += 1

    return puzzle, solved


# ============================================================
#  Виджет поля
# ============================================================

class SudokuWidget(QWidget):
    """Отрисовка судоку и взаимодействие мышью/клавиатурой."""

    cell_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(GRID * CELL_SIZE + 4, GRID * CELL_SIZE + 4)
        self.setFocusPolicy(Qt.StrongFocus)

        self.puzzle = [[0] * GRID for _ in range(GRID)]     # исходные (неизменяемые)
        self.solution = [[0] * GRID for _ in range(GRID)]   # правильное решение
        self.user = [[0] * GRID for _ in range(GRID)]        # введённое игроком
        self.notes = [[set() for _ in range(GRID)] for _ in range(GRID)]

        self.selected = None       # (r, c) выбранная клетка
        self.notes_mode = False
        self.wrong_cells = set()   # клетки с ошибками (подсветка)
        self.hint_used = 0

    def new_game(self, puzzle: list, solution: list):
        self.puzzle = [row[:] for row in puzzle]
        self.solution = [row[:] for row in solution]
        self.user = [[0] * GRID for _ in range(GRID)]
        self.notes = [[set() for _ in range(GRID)] for _ in range(GRID)]
        self.selected = None
        self.wrong_cells.clear()
        self.hint_used = 0
        self.update()
        self.cell_changed.emit()

    def set_data(self, puzzle, solution, user, notes, hint_used=0):
        self.puzzle = puzzle
        self.solution = solution
        self.user = user
        self.notes = [[set(n) if isinstance(n, list) else set() for n in row]
                       for row in notes]
        self.hint_used = hint_used
        self.wrong_cells.clear()
        self.update()

    def get_data(self) -> dict:
        return {
            "puzzle": self.puzzle,
            "solution": self.solution,
            "user": self.user,
            "notes": [[list(cell) for cell in row] for row in self.notes],
            "hint_used": self.hint_used,
        }

    # ------------------------------------------------------------
    #  Выбор клетки
    # ------------------------------------------------------------

    def cell_at(self, pos: QPointF) -> tuple:
        c = int(pos.x()) // CELL_SIZE
        r = int(pos.y()) // CELL_SIZE
        if 0 <= r < GRID and 0 <= c < GRID:
            return (r, c)
        return None

    def mousePressEvent(self, e):
        if e.button() != Qt.LeftButton:
            return
        cell = self.cell_at(e.position())
        if cell:
            self.selected = cell
            self.update()

    # ------------------------------------------------------------
    #  Клавиатура
    # ------------------------------------------------------------

    def keyPressEvent(self, e):
        key = e.key()

        if self.selected is None:
            super().keyPressEvent(e)
            return

        r, c = self.selected

        # Только редактируемые клетки
        if self.puzzle[r][c] != 0:
            super().keyPressEvent(e)
            return

        # Цифры 1-9
        if Qt.Key_1 <= key <= Qt.Key_9:
            num = key - Qt.Key_0
            if self.notes_mode:
                # Переключаем заметку
                if num in self.notes[r][c]:
                    self.notes[r][c].discard(num)
                else:
                    self.notes[r][c].add(num)
            else:
                # Устанавливаем цифру
                if self.user[r][c] == num:
                    self.user[r][c] = 0
                else:
                    self.user[r][c] = num
                    self.notes[r][c].clear()
                    # Проверка
                    if num != self.solution[r][c]:
                        self.wrong_cells.add((r, c))
                    else:
                        self.wrong_cells.discard((r, c))
            self.update()
            self.cell_changed.emit()
            e.accept()
            return

        # Delete / Backspace / 0 — очистить
        if key in (Qt.Key_Delete, Qt.Key_Backspace, Qt.Key_0):
            self.user[r][c] = 0
            self.notes[r][c].clear()
            self.wrong_cells.discard((r, c))
            self.update()
            self.cell_changed.emit()
            e.accept()
            return

        # Стрелки — навигация
        if key in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down):
            dr = dc = 0
            if key == Qt.Key_Left:  dc = -1
            if key == Qt.Key_Right: dc = 1
            if key == Qt.Key_Up:    dr = -1
            if key == Qt.Key_Down:  dr = 1
            nr = max(0, min(GRID - 1, r + dr))
            nc = max(0, min(GRID - 1, c + dc))
            self.selected = (nr, nc)
            self.update()
            e.accept()
            return

        # N — переключение режима заметок
        if key == Qt.Key_N:
            self.notes_mode = not self.notes_mode
            self.update()
            e.accept()
            return

        super().keyPressEvent(e)

    # ------------------------------------------------------------
    #  Отрисовка
    # ------------------------------------------------------------

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        # Фон
        p.fillRect(self.rect(), QColor("#0E1420"))

        accent = state().get("accent", "#6EC6FF")

        # Определяем клетки, связанные с выделенной (подсветка строки/столбца)
        highlight_cells = set()
        highlight_val = 0
        if self.selected:
            sr, sc = self.selected
            for i in range(GRID):
                highlight_cells.add((sr, i))
                highlight_cells.add((i, sc))
            # Клетки с таким же значением
            if self.user[sr][sc] != 0:
                highlight_val = self.user[sr][sc]
            elif self.puzzle[sr][sc] != 0:
                highlight_val = self.puzzle[sr][sc]
            if highlight_val:
                for r in range(GRID):
                    for c in range(GRID):
                        if self._cell_value(r, c) == highlight_val:
                            highlight_cells.add((r, c))

        # Рисуем клетки
        for r in range(GRID):
            for c in range(GRID):
                self._draw_cell(p, r, c, highlight_cells, highlight_val, accent)

        # Сетка
        self._draw_grid(p)

        # Выделение выбранной клетки
        if self.selected:
            sr, sc = self.selected
            rect = QRectF(sc * CELL_SIZE + 2, sr * CELL_SIZE + 2,
                          CELL_SIZE - 4, CELL_SIZE - 4)
            p.setBrush(Qt.NoBrush)
            pen = QPen(QColor(accent), 3)
            p.setPen(pen)
            p.drawRoundedRect(rect, 6, 6)

    def _cell_value(self, r: int, c: int) -> int:
        if self.puzzle[r][c] != 0:
            return self.puzzle[r][c]
        return self.user[r][c]

    def _draw_cell(self, p: QPainter, r: int, c: int,
                    highlight_cells: set, highlight_val: int, accent: str):
        x = c * CELL_SIZE + 2
        y = r * CELL_SIZE + 2
        w = CELL_SIZE - 4
        h = CELL_SIZE - 4

        # Фон клетки
        is_selected = self.selected == (r, c)
        is_highlight = (r, c) in highlight_cells and not is_selected

        bg = QColor(0, 0, 0, 0)
        if is_selected:
            bg = QColor(accent)
            bg.setAlpha(60)
        elif is_highlight:
            bg = QColor(255, 255, 255, 15)

        if bg.alpha() > 0:
            p.setBrush(QBrush(bg))
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(QRectF(x, y, w, h), 4, 4)

        # Значение
        fixed = self.puzzle[r][c] != 0
        user_val = self.user[r][c]
        val = self.puzzle[r][c] if fixed else user_val

        if val != 0:
            is_wrong = (r, c) in self.wrong_cells
            if fixed:
                color = QColor("#E0E6F0")
            elif is_wrong:
                color = QColor("#FF6B8A")
            else:
                color = QColor(accent)

            p.setPen(color)
            font = QFont()
            font.setPointSize(28)
            font.setBold(fixed)
            p.setFont(font)
            p.drawText(QRectF(x, y, w, h), Qt.AlignCenter, str(val))

        # Заметки (только если клетка пустая)
        elif self.notes[r][c] and not fixed and user_val == 0:
            self._draw_notes(p, r, c, x, y, w, h)

    def _draw_notes(self, p: QPainter, r: int, c: int,
                     x: float, y: float, w: float, h: float):
        """Рисует маленькие цифры в клетке (сетка 3×3)."""
        notes = self.notes[r][c]
        if not notes:
            return

        font = QFont()
        font.setPointSize(9)
        font.setBold(True)
        p.setFont(font)
        p.setPen(QColor(255, 255, 255, 130))

        sub_w = w / 3
        sub_h = h / 3
        for num in notes:
            if not (1 <= num <= 9):
                continue
            idx = num - 1
            nr = idx // 3
            nc = idx % 3
            nx = x + nc * sub_w
            ny = y + nr * sub_h
            p.drawText(QRectF(nx, ny, sub_w, sub_h),
                       Qt.AlignCenter, str(num))

    def _draw_grid(self, p: QPainter):
        """Рисует линии сетки."""
        # Тонкие линии
        pen = QPen(QColor(255, 255, 255, 40), 1)
        p.setPen(pen)
        for i in range(1, GRID):
            x = i * CELL_SIZE + 2
            y = i * CELL_SIZE + 2
            p.drawLine(QPointF(x, 2), QPointF(x, GRID * CELL_SIZE + 2))
            p.drawLine(QPointF(2, y), QPointF(GRID * CELL_SIZE + 2, y))

        # Толстые линии (блоки 3×3)
        pen = QPen(QColor(255, 255, 255, 120), 3)
        p.setPen(pen)
        for i in range(0, GRID + 1, 3):
            x = i * CELL_SIZE + 2
            y = i * CELL_SIZE + 2
            p.drawLine(QPointF(x, 2), QPointF(x, GRID * CELL_SIZE + 2))
            p.drawLine(QPointF(2, y), QPointF(GRID * CELL_SIZE + 2, y))

        # Внешняя рамка
        pen = QPen(QColor(255, 255, 255, 180), 3)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawRect(QRectF(2, 2, GRID * CELL_SIZE, GRID * CELL_SIZE))


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
        "difficulty": "medium",
        "start_time": 0.0,
        "timer_running": False,
        "paused": False,
        "elapsed": 0,
        "completed": 0,
        "stats": {},
    }

    # ---- Загрузка статистики ----
    if vfs:
        try:
            raw = vfs.read_text(STATS_PATH, "")
            if raw.strip():
                data = json.loads(raw)
                st["completed"] = data.get("completed", 0)
                st["stats"] = data.get("stats", {})
        except Exception:
            pass

    def save_stats():
        if vfs is None:
            return
        try:
            vfs.mkdir("/Documents")
            vfs.write_text(STATS_PATH,
                json.dumps({"completed": st["completed"],
                            "stats": st["stats"]},
                            ensure_ascii=False, indent=2))
        except Exception:
            pass

    # ---- Левая панель — поле ----
    left = QWidget()
    ll = QVBoxLayout(left)
    ll.setContentsMargins(30, 30, 30, 30)
    ll.setSpacing(16)
    ll.setAlignment(Qt.AlignCenter)

    board = SudokuWidget()
    ll.addWidget(board, 0, Qt.AlignCenter)

    hint = QLabel("ЛКМ — выбрать клетку  ·  Цифры 1-9 — ввести  ·  "
                   "N — заметки  ·  Стрелки — навигация  ·  Del — очистить")
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

    title = QLabel("🔢  Судоку")
    title.setStyleSheet("color: white; font-size: 20px; font-weight: 600; padding: 2px;")
    rl.addWidget(title)

    hint2 = QLabel("Заполни все клетки цифрами 1-9.\nКаждая цифра — один раз в строке, столбце и блоке 3×3.")
    hint2.setStyleSheet("color: rgba(255,255,255,0.55); font-size: 12px;")
    hint2.setWordWrap(True)
    rl.addWidget(hint2)

    rl.addSpacing(10)

    # ---- Сложность ----
    diff_lbl = QLabel("СЛОЖНОСТЬ")
    diff_lbl.setStyleSheet("""
        color: rgba(255,255,255,0.45);
        font-size: 10px;
        font-weight: 700;
        letter-spacing: 1.5px;
    """)
    rl.addWidget(diff_lbl)

    diff_combo = QComboBox()
    for key, data in DIFFICULTY.items():
        diff_combo.addItem(data["name"], key)
    diff_combo.setCurrentIndex(1)
    diff_combo.setStyleSheet("""
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
    rl.addWidget(diff_combo)

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

    time_box, time_val = make_metric("ВРЕМЯ", "clock", "110,198,255")
    rl.addWidget(time_box)

    filled_box, filled_val = make_metric("ЗАПОЛНЕНО", "grid", "110,231,183")
    rl.addWidget(filled_box)

    solved_box, solved_val = make_metric("РЕШЕНО ИГР", "star", "255,184,108")
    rl.addWidget(solved_box)

    rl.addSpacing(10)

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

    hint_btn = QPushButton("💡  Подсказка")
    hint_btn.setCursor(Qt.PointingHandCursor)
    hint_btn.setFixedHeight(38)
    hint_btn.setStyleSheet("""
        QPushButton {
            background: rgba(255,184,108,0.18);
            color: #FFB86C;
            border: 1px solid rgba(255,184,108,0.45);
            border-radius: 10px;
            font-size: 12px;
        }
        QPushButton:hover { background: rgba(255,184,108,0.35); color: white; }
    """)
    rl.addWidget(hint_btn)

    check_btn = QPushButton("✓  Проверить")
    check_btn.setCursor(Qt.PointingHandCursor)
    check_btn.setFixedHeight(38)
    check_btn.setStyleSheet("""
        QPushButton {
            background: rgba(110,231,183,0.18);
            color: #6EE7B7;
            border: 1px solid rgba(110,231,183,0.45);
            border-radius: 10px;
            font-size: 12px;
        }
        QPushButton:hover { background: rgba(110,231,183,0.35); color: white; }
    """)
    rl.addWidget(check_btn)

    notes_btn = QPushButton("✎  Режим заметок: ВЫКЛ")
    notes_btn.setCursor(Qt.PointingHandCursor)
    notes_btn.setFixedHeight(36)
    notes_btn.setStyleSheet("""
        QPushButton {
            background: rgba(255,255,255,0.06);
            color: white;
            border: 1px solid rgba(255,255,255,0.12);
            border-radius: 10px;
            font-size: 12px;
        }
        QPushButton:hover { background: rgba(255,255,255,0.18); }
    """)
    rl.addWidget(notes_btn)

    rl.addStretch(1)

    h.addWidget(right)

    # ============================================================
    #  Логика
    # ============================================================

    timer = QTimer(root)
    timer.setInterval(1000)

    def update_metrics():
        # Время
        if st["timer_running"]:
            st["elapsed"] = int(time.time() - st["start_time"])
        secs = st["elapsed"]
        m = secs // 60
        s = secs % 60
        time_val.setText(f"{m:02d}:{s:02d}")

        # Заполнено
        filled = 0
        for r in range(GRID):
            for c in range(GRID):
                if board.puzzle[r][c] != 0 or board.user[r][c] != 0:
                    filled += 1
        filled_val.setText(f"{filled} / 81")

        # Решено
        solved_val.setText(str(st["completed"]))

    def on_tick():
        if st["timer_running"]:
            update_metrics()

    timer.timeout.connect(on_tick)

    def save_game():
        if vfs is None:
            return
        try:
            vfs.mkdir("/Documents")
            data = board.get_data()
            data["difficulty"] = st["difficulty"]
            data["elapsed"] = st["elapsed"]
            data["saved_at"] = time.time()
            vfs.write_text(SAVE_PATH,
                            json.dumps(data, ensure_ascii=False, indent=2))
        except Exception as e:
            print(f"[Sudoku] save: {e}")

    def load_game() -> bool:
        if vfs is None:
            return False
        try:
            raw = vfs.read_text(SAVE_PATH, "")
            if not raw.strip():
                return False
            data = json.loads(raw)
            board.set_data(
                data["puzzle"], data["solution"],
                data["user"], data["notes"],
                data.get("hint_used", 0))
            st["difficulty"] = data.get("difficulty", "medium")
            st["elapsed"] = data.get("elapsed", 0)
            # Обновляем комбо
            idx = diff_combo.findData(st["difficulty"])
            if idx >= 0:
                diff_combo.blockSignals(True)
                diff_combo.setCurrentIndex(idx)
                diff_combo.blockSignals(False)
            # Запускаем таймер
            st["start_time"] = time.time() - st["elapsed"]
            st["timer_running"] = True
            timer.start()
            update_metrics()
            return True
        except Exception as e:
            print(f"[Sudoku] load: {e}")
            return False

    def new_game():
        timer.stop()
        st["timer_running"] = False
        st["elapsed"] = 0

        key = diff_combo.currentData()
        st["difficulty"] = key

        # Показываем "Генерация…"
        QMessageBox.information(root, "Судоку",
            "Генерация новой головоломки…\n(может занять 1-2 секунды)")

        # Генерируем
        puzzle, solution = generate_sudoku(key)
        board.new_game(puzzle, solution)

        st["start_time"] = time.time()
        st["timer_running"] = True
        timer.start()
        update_metrics()

    def check_solution():
        # Всё ли заполнено
        for r in range(GRID):
            for c in range(GRID):
                val = board.user[r][c] if board.puzzle[r][c] == 0 else board.puzzle[r][c]
                if val == 0:
                    QMessageBox.information(root, "Судоку",
                        "Ещё не все клетки заполнены.")
                    return

        # Проверка
        for r in range(GRID):
            for c in range(GRID):
                val = board.user[r][c] if board.puzzle[r][c] == 0 else board.puzzle[r][c]
                if val != board.solution[r][c]:
                    QMessageBox.warning(root, "Судоку",
                        f"Ошибка в клетке R{r+1} C{c+1}.")
                    board.selected = (r, c)
                    board.update()
                    return

        # Победа!
        on_win()

    def on_win():
        timer.stop()
        st["timer_running"] = False
        st["completed"] += 1

        # Статистика по сложности
        key = st["difficulty"]
        stats = st["stats"].setdefault(key, {"count": 0, "best_time": 0})
        stats["count"] += 1
        best = stats.get("best_time", 0)
        if best == 0 or st["elapsed"] < best:
            stats["best_time"] = st["elapsed"]
            new_record = True
        else:
            new_record = False

        save_stats()
        update_metrics()

        m = st["elapsed"] // 60
        s = st["elapsed"] % 60

        if desktop and hasattr(desktop, "notifications"):
            desktop.notifications.push(
                "🏆 Судоку решена!",
                f"{DIFFICULTY[key]['name']}: {m:02d}:{s:02d}"
                + ("  (новый рекорд!)" if new_record else ""))

        QMessageBox.information(root, "🏆 Победа!",
            f"Судоку решена!\n\n"
            f"Сложность: {DIFFICULTY[key]['name']}\n"
            f"Время: {m:02d}:{s:02d}\n"
            f"{'🏆 Новый рекорд!' if new_record else ''}")

    def use_hint():
        # Находим все пустые клетки
        empty = [(r, c) for r in range(GRID) for c in range(GRID)
                 if board.puzzle[r][c] == 0 and board.user[r][c] != board.solution[r][c]]

        if not empty:
            QMessageBox.information(root, "Судоку",
                "Нечего подсказывать — всё заполнено правильно!")
            return

        r, c = random.choice(empty)
        board.user[r][c] = board.solution[r][c]
        board.notes[r][c].clear()
        board.wrong_cells.discard((r, c))
        board.selected = (r, c)
        board.hint_used += 1
        board.update()
        update_metrics()

        if desktop and hasattr(desktop, "notifications"):
            desktop.notifications.push("💡 Подсказка",
                f"R{r+1} C{c+1} = {board.solution[r][c]}")

        # Проверка победы
        all_filled = all(
            (board.puzzle[r][c] != 0) or (board.user[r][c] != 0)
            for r in range(GRID) for c in range(GRID)
        )
        if all_filled:
            correct = all(
                (board.puzzle[r][c] != 0 and board.puzzle[r][c] == board.solution[r][c])
                or (board.puzzle[r][c] == 0 and board.user[r][c] == board.solution[r][c])
                for r in range(GRID) for c in range(GRID)
            )
            if correct:
                on_win()

    def toggle_notes():
        board.notes_mode = not board.notes_mode
        board.update()
        notes_btn.setText(
            f"✎  Режим заметок: {'ВКЛ' if board.notes_mode else 'ВЫКЛ'}")

    def on_cell_changed():
        update_metrics()
        # Автосохранение
        save_game()
        # Автопроверка победы
        all_filled = all(
            (board.puzzle[r][c] != 0) or (board.user[r][c] != 0)
            for r in range(GRID) for c in range(GRID)
        )
        if all_filled:
            correct = all(
                (board.puzzle[r][c] != 0 and board.puzzle[r][c] == board.solution[r][c])
                or (board.puzzle[r][c] == 0 and board.user[r][c] == board.solution[r][c])
                for r in range(GRID) for c in range(GRID)
            )
            if correct:
                on_win()

    # ---- Связи ----
    board.cell_changed.connect(on_cell_changed)
    new_btn.clicked.connect(new_game)
    hint_btn.clicked.connect(use_hint)
    check_btn.clicked.connect(check_solution)
    notes_btn.clicked.connect(toggle_notes)

    # Автосохранение каждые 10 сек
    autosave = QTimer(root)
    autosave.setInterval(10000)
    autosave.timeout.connect(save_game)
    autosave.start()

    # ---- Стартовая загрузка или новая игра ----
    if not load_game():
        new_game()
    else:
        update_metrics()

    QTimer.singleShot(200, board.setFocus)

    return root