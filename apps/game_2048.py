"""
MountOS — Игра 2048.

Полная реализация классической 2048:
  • Скольжение плиток стрелками или WASD
  • Слияние одинаковых чисел
  • Красивые анимации перемещения и появления
  • Счёт + рекорд (сохраняется в VFS)
  • Отмена последнего хода (Ctrl+Z)
  • Автосохранение игры
  • Свои цвета для каждого числа
  • Победа при 2048, продолжение по желанию

Установка: apps/game_2048.py + перезапуск MountOS.
"""

import json
import random
import time
import copy

from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QSizePolicy, QMessageBox
from PySide6.QtCore import (Qt, QTimer, QRectF, QPointF, QPropertyAnimation,
                             QEasingCurve, QParallelAnimationGroup, Signal)
from PySide6.QtGui import (QPainter, QColor, QPen, QBrush, QFont,
                            QPainterPath, QLinearGradient, QKeyEvent)

from ui.icons import get_icon
from ui.settings_state import state

APP_NAME = "2048"
APP_ICON = "grid"
APP_VERSION = "1.0"
APP_AUTHOR = "MountOS"


SAVE_PATH = "/Documents/2048_save.json"
HIGHSCORE_PATH = "/Documents/2048_highscore.txt"

GRID_SIZE = 4
CELL_SIZE = 110
CELL_MARGIN = 12


# ============================================================
#  Цвета плиток
# ============================================================

TILE_COLORS = {
    0:    ("#1E2438", "#1E2438"),
    2:    ("#EEE4DA", "#776E65"),
    4:    ("#EDE0C8", "#776E65"),
    8:    ("#F2B179", "#FFFFFF"),
    16:   ("#F59563", "#FFFFFF"),
    32:   ("#F67C5F", "#FFFFFF"),
    64:   ("#F65E3B", "#FFFFFF"),
    128:  ("#EDCF72", "#FFFFFF"),
    256:  ("#EDCC61", "#FFFFFF"),
    512:  ("#EDC850", "#FFFFFF"),
    1024: ("#EDC53F", "#FFFFFF"),
    2048: ("#EDC22E", "#FFFFFF"),
    4096: ("#3C3A32", "#FFFFFF"),
    8192: ("#2E2C26", "#FFFFFF"),
}


def tile_colors(value: int) -> tuple:
    """Возвращает (bg, fg) для значения плитки."""
    if value in TILE_COLORS:
        return TILE_COLORS[value]
    return TILE_COLORS[8192]


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
#  Игровое поле
# ============================================================

class Board:
    """Логика 2048 — независима от UI."""

    def __init__(self):
        self.grid = [[0] * GRID_SIZE for _ in range(GRID_SIZE)]
        self.score = 0
        self.won = False
        self.game_over = False
        self.moves = 0

    def clone(self):
        b = Board()
        b.grid = [row[:] for row in self.grid]
        b.score = self.score
        b.won = self.won
        b.game_over = self.game_over
        b.moves = self.moves
        return b

    def to_dict(self) -> dict:
        return {
            "grid": self.grid,
            "score": self.score,
            "won": self.won,
            "game_over": self.game_over,
            "moves": self.moves,
        }

    def from_dict(self, d: dict):
        self.grid = d.get("grid", [[0] * GRID_SIZE for _ in range(GRID_SIZE)])
        self.score = d.get("score", 0)
        self.won = d.get("won", False)
        self.game_over = d.get("game_over", False)
        self.moves = d.get("moves", 0)

    def empty_cells(self) -> list:
        return [(r, c) for r in range(GRID_SIZE)
                       for c in range(GRID_SIZE) if self.grid[r][c] == 0]

    def spawn_random(self) -> tuple:
        """Добавляет 2 или 4 в случайную пустую клетку. Возвращает (r, c, value)."""
        cells = self.empty_cells()
        if not cells:
            return None
        r, c = random.choice(cells)
        self.grid[r][c] = 2 if random.random() < 0.9 else 4
        return (r, c, self.grid[r][c])

    def _slide_row_left(self, row: list) -> tuple:
        """Скользит и сливает одну строку влево. Возвращает (new_row, score_delta, moved)."""
        # Убираем нули
        nonzero = [v for v in row if v != 0]
        new_row = []
        score_delta = 0
        i = 0
        while i < len(nonzero):
            if i + 1 < len(nonzero) and nonzero[i] == nonzero[i + 1]:
                merged = nonzero[i] * 2
                new_row.append(merged)
                score_delta += merged
                if merged == 2048:
                    self.won = True
                i += 2
            else:
                new_row.append(nonzero[i])
                i += 1
        # Дополняем нулями
        new_row += [0] * (GRID_SIZE - len(new_row))
        moved = (new_row != row)
        return new_row, score_delta, moved

    def move(self, direction: str) -> bool:
        """
        direction: 'left' | 'right' | 'up' | 'down'
        Возвращает True, если что-то сдвинулось.
        """
        if self.game_over:
            return False

        moved_any = False
        score_gained = 0

        if direction in ("left", "right"):
            for r in range(GRID_SIZE):
                row = self.grid[r][:]
                if direction == "right":
                    row = row[::-1]
                new_row, delta, moved = self._slide_row_left(row)
                if direction == "right":
                    new_row = new_row[::-1]
                if moved:
                    self.grid[r] = new_row
                    moved_any = True
                score_gained += delta

        else:  # up / down
            for c in range(GRID_SIZE):
                col = [self.grid[r][c] for r in range(GRID_SIZE)]
                if direction == "down":
                    col = col[::-1]
                new_col, delta, moved = self._slide_row_left(col)
                if direction == "down":
                    new_col = new_col[::-1]
                if moved:
                    for r in range(GRID_SIZE):
                        self.grid[r][c] = new_col[r]
                    moved_any = True
                score_gained += delta

        if moved_any:
            self.score += score_gained
            self.moves += 1
            if not self.can_move():
                self.game_over = True

        return moved_any

    def can_move(self) -> bool:
        if self.empty_cells():
            return True
        # Есть ли рядом одинаковые
        for r in range(GRID_SIZE):
            for c in range(GRID_SIZE):
                v = self.grid[r][c]
                if c + 1 < GRID_SIZE and self.grid[r][c + 1] == v:
                    return True
                if r + 1 < GRID_SIZE and self.grid[r + 1][c] == v:
                    return True
        return False


# ============================================================
#  Виджет игрового поля
# ============================================================

class BoardWidget(QWidget):
    """Отрисовка поля 2048 и анимация плиток."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(GRID_SIZE * CELL_SIZE + 5 * CELL_MARGIN,
                          GRID_SIZE * CELL_SIZE + 5 * CELL_MARGIN)
        self.setFocusPolicy(Qt.StrongFocus)

        self.board = Board()
        self._spawn_anim = {}   # (r, c) -> 0..1 анимация появления
        self._merge_anim = {}   # (r, c) -> 0..1 анимация пульса при слиянии

        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self._anim_tick)
        self._anim_timer.setInterval(16)   # 60 FPS

    def new_game(self):
        self.board = Board()
        self._spawn_anim.clear()
        self._merge_anim.clear()
        self.spawn_tile()
        self.spawn_tile()
        self.update()

    def spawn_tile(self):
        result = self.board.spawn_random()
        if result:
            r, c, v = result
            self._spawn_anim[(r, c)] = 0.0
            if not self._anim_timer.isActive():
                self._anim_timer.start()

    def move(self, direction: str) -> bool:
        """Делает ход. Возвращает True если что-то сдвинулось."""
        old_grid = [row[:] for row in self.board.grid]
        moved = self.board.move(direction)
        if moved:
            # Помечаем "новые" плитки, которые увеличились (мерж)
            for r in range(GRID_SIZE):
                for c in range(GRID_SIZE):
                    old_v = old_grid[r][c]
                    new_v = self.board.grid[r][c]
                    if new_v != 0 and new_v != old_v and new_v == old_v * 2:
                        self._merge_anim[(r, c)] = 0.0
            self.spawn_tile()
            if not self._anim_timer.isActive():
                self._anim_timer.start()
            self.update()
            return True
        return False

    def _anim_tick(self):
        """Обновление анимаций появления/слияния."""
        any_active = False
        # Появление
        finished_spawn = []
        for key in list(self._spawn_anim.keys()):
            self._spawn_anim[key] += 0.08
            if self._spawn_anim[key] >= 1.0:
                finished_spawn.append(key)
            else:
                any_active = True
        for k in finished_spawn:
            del self._spawn_anim[k]

        # Слияние
        finished_merge = []
        for key in list(self._merge_anim.keys()):
            self._merge_anim[key] += 0.1
            if self._merge_anim[key] >= 1.0:
                finished_merge.append(key)
            else:
                any_active = True
        for k in finished_merge:
            del self._merge_anim[k]

        self.update()
        if not any_active:
            self._anim_timer.stop()

    def cell_rect(self, r: int, c: int) -> QRectF:
        x = CELL_MARGIN + c * (CELL_SIZE + CELL_MARGIN)
        y = CELL_MARGIN + r * (CELL_SIZE + CELL_MARGIN)
        return QRectF(x, y, CELL_SIZE, CELL_SIZE)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        # Фон поля
        p.setBrush(QBrush(QColor("#0E1420")))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(self.rect(), 12, 12)

        # Пустые ячейки
        for r in range(GRID_SIZE):
            for c in range(GRID_SIZE):
                rect = self.cell_rect(r, c)
                p.setBrush(QBrush(QColor("#1E2438")))
                p.setPen(Qt.NoPen)
                p.drawRoundedRect(rect, 8, 8)

        # Плитки
        for r in range(GRID_SIZE):
            for c in range(GRID_SIZE):
                v = self.board.grid[r][c]
                if v == 0:
                    continue

                rect = self.cell_rect(r, c)
                bg, fg = tile_colors(v)

                # Анимация появления — масштаб
                if (r, c) in self._spawn_anim:
                    t = self._spawn_anim[(r, c)]
                    scale = 0.3 + 0.7 * t
                    center = rect.center()
                    w = rect.width() * scale
                    h = rect.height() * scale
                    rect = QRectF(center.x() - w/2, center.y() - h/2, w, h)

                # Анимация слияния — пульс
                if (r, c) in self._merge_anim:
                    t = self._merge_anim[(r, c)]
                    # Пульс 1.0 → 1.15 → 1.0
                    pulse = 1 + 0.15 * (1 - abs(2 * t - 1))
                    center = rect.center()
                    w = rect.width() * pulse
                    h = rect.height() * pulse
                    rect = QRectF(center.x() - w/2, center.y() - h/2, w, h)

                # Рисуем плитку
                p.setBrush(QBrush(QColor(bg)))
                p.setPen(Qt.NoPen)
                p.drawRoundedRect(rect, 8, 8)

                # Текст
                p.setPen(QColor(fg))
                font_size = 40
                if v >= 100:
                    font_size = 36
                if v >= 1000:
                    font_size = 30
                if v >= 10000:
                    font_size = 24
                font = QFont()
                font.setPointSize(font_size)
                font.setBold(True)
                p.setFont(font)
                p.drawText(rect, Qt.AlignCenter, str(v))

    # ---- Управление клавишами ----
    def keyPressEvent(self, e):
        key = e.key()
        direction = None
        if key in (Qt.Key_Left, Qt.Key_A):
            direction = "left"
        elif key in (Qt.Key_Right, Qt.Key_D):
            direction = "right"
        elif key in (Qt.Key_Up, Qt.Key_W):
            direction = "up"
        elif key in (Qt.Key_Down, Qt.Key_S):
            direction = "down"

        if direction:
            self.move(direction)
            e.accept()
            return

        super().keyPressEvent(e)


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

    # ---- Левая панель — поле ----
    left = QWidget()
    ll = QVBoxLayout(left)
    ll.setContentsMargins(30, 30, 30, 30)
    ll.setSpacing(16)
    ll.setAlignment(Qt.AlignCenter)

    # Поле
    board_widget = BoardWidget()
    ll.addWidget(board_widget, 0, Qt.AlignCenter)

    # Подсказка
    hint = QLabel("Управление: ← → ↑ ↓ или WASD    ·    Ctrl+Z — отмена")
    hint.setAlignment(Qt.AlignCenter)
    hint.setStyleSheet("""
        color: rgba(255,255,255,0.45);
        font-size: 11px;
        padding: 4px;
    """)
    ll.addWidget(hint)

    h.addWidget(left, 1)

    # ---- Правая панель — счёт + кнопки ----
    right = QWidget()
    right.setFixedWidth(280)
    right.setStyleSheet("""
        background: rgba(255,255,255,0.04);
        border-left: 1px solid rgba(255,255,255,0.08);
    """)
    rl = QVBoxLayout(right)
    rl.setContentsMargins(20, 24, 20, 24)
    rl.setSpacing(14)

    title = QLabel("🎮  2048")
    title.setStyleSheet("color: white; font-size: 20px; font-weight: 600; padding: 2px;")
    rl.addWidget(title)

    hint2 = QLabel("Собирай плитки, объединяй одинаковые.\nЦель — 2048!")
    hint2.setStyleSheet("color: rgba(255,255,255,0.55); font-size: 12px;")
    hint2.setWordWrap(True)
    rl.addWidget(hint2)

    rl.addSpacing(10)

    # Счёт
    score_box = QWidget()
    score_box.setStyleSheet("""
        QWidget {
            background: rgba(110,198,255,0.12);
            border: 1px solid rgba(110,198,255,0.35);
            border-radius: 12px;
        }
    """)
    sbl = QVBoxLayout(score_box)
    sbl.setContentsMargins(14, 12, 14, 12)
    sbl.setSpacing(4)

    s_lbl = QLabel("СЧЁТ")
    s_lbl.setStyleSheet("""
        color: rgba(255,255,255,0.55);
        font-size: 10px;
        font-weight: 700;
        letter-spacing: 1.5px;
        background: transparent;
        border: none;
    """)
    sbl.addWidget(s_lbl)

    score_val = QLabel("0")
    score_val.setStyleSheet("""
        color: white;
        font-size: 32px;
        font-weight: 300;
        background: transparent;
        border: none;
    """)
    sbl.addWidget(score_val)

    rl.addWidget(score_box)

    # Рекорд
    hs_box = QWidget()
    hs_box.setStyleSheet("""
        QWidget {
            background: rgba(255,184,108,0.12);
            border: 1px solid rgba(255,184,108,0.35);
            border-radius: 12px;
        }
    """)
    hsl = QVBoxLayout(hs_box)
    hsl.setContentsMargins(14, 12, 14, 12)
    hsl.setSpacing(4)

    hs_lbl = QLabel("РЕКОРД")
    hs_lbl.setStyleSheet("""
        color: rgba(255,255,255,0.55);
        font-size: 10px;
        font-weight: 700;
        letter-spacing: 1.5px;
        background: transparent;
        border: none;
    """)
    hsl.addWidget(hs_lbl)

    hs_val = QLabel("0")
    hs_val.setStyleSheet("""
        color: #FFB86C;
        font-size: 32px;
        font-weight: 300;
        background: transparent;
        border: none;
    """)
    hsl.addWidget(hs_val)

    rl.addWidget(hs_box)

    rl.addSpacing(20)

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

    undo_btn = QPushButton("↶  Отменить ход")
    undo_btn.setCursor(Qt.PointingHandCursor)
    undo_btn.setFixedHeight(38)
    undo_btn.setStyleSheet("""
        QPushButton {
            background: rgba(255,255,255,0.06);
            color: white;
            border: 1px solid rgba(255,255,255,0.12);
            border-radius: 10px;
            font-size: 12px;
        }
        QPushButton:hover { background: rgba(255,255,255,0.18); }
    """)
    rl.addWidget(undo_btn)

    rl.addStretch(1)

    # Информация
    info_lbl = QLabel("")
    info_lbl.setStyleSheet("""
        color: rgba(255,255,255,0.45);
        font-size: 11px;
        padding: 8px;
        background: rgba(0,0,0,0.20);
        border-radius: 10px;
    """)
    info_lbl.setWordWrap(True)
    rl.addWidget(info_lbl)

    h.addWidget(right)

    # ============================================================
    #  Логика
    # ============================================================

    st = {
        "highscore": 0,
        "history": [],   # для отмены
        "won_shown": False,
    }

    # Загружаем рекорд
    if vfs:
        try:
            raw = vfs.read_text(HIGHSCORE_PATH, "0")
            st["highscore"] = int(raw.strip() or "0")
        except Exception:
            st["highscore"] = 0
    hs_val.setText(str(st["highscore"]))

    def save_highscore():
        if vfs is None:
            return
        try:
            vfs.mkdir("/Documents")
            vfs.write_text(HIGHSCORE_PATH, str(st["highscore"]))
        except Exception:
            pass

    def save_game():
        if vfs is None:
            return
        try:
            vfs.mkdir("/Documents")
            data = {
                "board": board_widget.board.to_dict(),
                "highscore": st["highscore"],
                "saved_at": time.time(),
            }
            vfs.write_text(SAVE_PATH, json.dumps(data, ensure_ascii=False, indent=2))
        except Exception as e:
            print(f"[2048] save: {e}")

    def load_game() -> bool:
        if vfs is None:
            return False
        try:
            raw = vfs.read_text(SAVE_PATH, "")
            if not raw.strip():
                return False
            data = json.loads(raw)
            board_widget.board.from_dict(data.get("board", {}))
            st["highscore"] = max(st["highscore"], data.get("highscore", 0))
            hs_val.setText(str(st["highscore"]))
            score_val.setText(str(board_widget.board.score))
            board_widget.update()
            return True
        except Exception as e:
            print(f"[2048] load: {e}")
            return False

    def update_info():
        b = board_widget.board
        info_lbl.setText(
            f"Ходов: {b.moves}\n"
            f"Пустых: {len(b.empty_cells())}\n"
            f"Состояние: {'Игра идёт' if not b.game_over else 'Проигрыш'}"
        )

    def on_move_done(moved: bool):
        b = board_widget.board

        # Обновляем счёт
        score_val.setText(str(b.score))

        # Обновляем рекорд
        if b.score > st["highscore"]:
            st["highscore"] = b.score
            hs_val.setText(str(st["highscore"]))
            save_highscore()

        # Проверка победы
        if b.won and not st["won_shown"]:
            st["won_shown"] = True
            QTimer.singleShot(300, lambda: show_win_dialog())

        # Проверка проигрыша
        if b.game_over:
            QTimer.singleShot(300, show_game_over)

        update_info()
        save_game()

    def show_win_dialog():
        ans = QMessageBox.question(
            root, "🎉 Победа!",
            "Ты собрал 2048!\n\nПродолжить игру?",
            QMessageBox.Yes | QMessageBox.No)
        if ans == QMessageBox.No:
            new_game()

    def show_game_over():
        ans = QMessageBox.question(
            root, "Игра окончена",
            f"Счёт: {board_widget.board.score}\n"
            f"Рекорд: {st['highscore']}\n\n"
            f"Начать новую игру?",
            QMessageBox.Yes | QMessageBox.No)
        if ans == QMessageBox.Yes:
            new_game()

    def new_game():
        st["history"].clear()
        st["won_shown"] = False
        board_widget.new_game()
        score_val.setText("0")
        update_info()
        save_game()

    def undo():
        if not st["history"]:
            return
        prev = st["history"].pop()
        board_widget.board.from_dict(prev)
        score_val.setText(str(board_widget.board.score))
        board_widget.update()
        update_info()
        save_game()

    # Обёртка над board_widget.move — сохраняем историю
    original_move = board_widget.move

    def wrapped_move(direction: str) -> bool:
        # Сохраняем состояние до хода
        st["history"].append(board_widget.board.to_dict())
        if len(st["history"]) > 50:
            st["history"].pop(0)

        moved = original_move(direction)
        if not moved:
            # Ход не сделан — убираем из истории
            st["history"].pop()
        else:
            on_move_done(True)
        return moved

    board_widget.move = wrapped_move

    # Связи
    new_btn.clicked.connect(new_game)
    undo_btn.clicked.connect(undo)

    # Отмена по Ctrl+Z — перехватываем в board_widget
    original_key = board_widget.keyPressEvent

    def new_key(e):
        if e.key() == Qt.Key_Z and e.modifiers() & Qt.ControlModifier:
            undo()
            e.accept()
            return
        if e.key() == Qt.Key_R:
            new_game()
            e.accept()
            return
        original_key(e)

    board_widget.keyPressEvent = new_key

    # Автосохранение каждые 5 сек
    autosave = QTimer(root)
    autosave.setInterval(5000)
    autosave.timeout.connect(save_game)
    autosave.start()

    # Стартовая загрузка / новая игра
    if not load_game():
        new_game()
    else:
        # Если сохранённая игра была окончена — начинаем новую
        if board_widget.board.game_over:
            new_game()
        else:
            update_info()

    # Фокус
    QTimer.singleShot(200, board_widget.setFocus)

    return root