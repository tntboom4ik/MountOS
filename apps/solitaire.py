"""
MountOS — Пасьянс «Косынка» (Klondike Solitaire).
"""
import json
import random
import time
from datetime import datetime

from PySide6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QLabel,
                                QPushButton, QMessageBox, QSizePolicy,
                                QComboBox)
from PySide6.QtCore import Qt, QTimer, QRectF, QPointF, QPoint, Signal
from PySide6.QtGui import (QPainter, QColor, QPen, QBrush, QFont,
                            QPainterPath, QLinearGradient, QPolygonF)

from ui.icons import get_icon
from ui.settings_state import state

APP_NAME = "Косынка"
APP_ICON = "grid"
APP_VERSION = "1.0"
APP_AUTHOR = "MountOS"


SAVE_PATH = "/Documents/solitaire_save.json"
RECORDS_PATH = "/Documents/solitaire_records.json"


# ============================================================
#  Константы
# ============================================================

CARD_W = 80
CARD_H = 112
STACK_OFFSET = 26          # вертикальный сдвиг открытых карт в колонке
FACEDOWN_OFFSET = 14       # сдвиг закрытых карт
GAP = 16

SUITS = ["♠", "♥", "♦", "♣"]
RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]

# Цвета карт
RED = QColor("#D63A5B")
BLACK = QColor("#1A1F35")


def is_red(card: tuple) -> bool:
    """card = (suit, rank_index)."""
    return card[0] in ("♥", "♦")


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
#  Игровая модель
# ============================================================

class SolitaireGame:
    """Логика Косынки."""

    def __init__(self):
        self.tableau = [[] for _ in range(7)]    # 7 колонок, каждая — список карт
        self.foundations = [[] for _ in range(4)] # 4 "дома" по мастям
        self.stock = []                            # колода для переворота
        self.waste = []                            # открытые из колоды
        self.face_up = []                          # какие карты открыты (по позиции)
        self.moves = 0
        self.score = 0
        self.won = False
        self.recycle_count = 0

        # Для отмены
        self.history = []

    # ------------------------------------------------------------

    def new_game(self):
        self.tableau = [[] for _ in range(7)]
        self.foundations = [[] for _ in range(4)]
        self.stock = []
        self.waste = []
        self.face_up = []
        self.moves = 0
        self.score = 0
        self.won = False
        self.recycle_count = 0
        self.history = []

        # Создаём колоду
        deck = []
        for suit in SUITS:
            for rank_idx in range(13):    # 0=A, 12=K
                deck.append((suit, rank_idx))
        random.shuffle(deck)

        # Раскладываем в 7 колонок: col i — i+1 карт (последняя открыта)
        for col in range(7):
            for j in range(col + 1):
                card = deck.pop()
                self.tableau[col].append(card)
                # последняя открыта
                self.face_up.append((col, j, j == col))
        # Преобразуем в более удобную структуру
        self.face_up = []  # сброс, будем хранить иначе

        # Отдельный список: открытость карт в колонках
        # (индекс [col][i] = True если открыта)
        self.visible = [[False] * len(self.tableau[c]) for c in range(7)]
        for c in range(7):
            if self.tableau[c]:
                self.visible[c][-1] = True

        # Оставшиеся карты — в stock
        self.stock = deck

    # ------------------------------------------------------------

    def snapshot(self):
        """Сохраняет состояние для отмены."""
        return {
            "tableau": [list(col) for col in self.tableau],
            "foundations": [list(f) for f in self.foundations],
            "stock": list(self.stock),
            "waste": list(self.waste),
            "visible": [list(v) for v in self.visible],
            "moves": self.moves,
            "score": self.score,
            "recycle_count": self.recycle_count,
        }

    def restore(self, snap: dict):
        self.tableau = [list(col) for col in snap["tableau"]]
        self.foundations = [list(f) for f in snap["foundations"]]
        self.stock = list(snap["stock"])
        self.waste = list(snap["waste"])
        self.visible = [list(v) for v in snap["visible"]]
        self.moves = snap["moves"]
        self.score = snap["score"]
        self.recycle_count = snap.get("recycle_count", 0)

    def push_history(self):
        self.history.append(self.snapshot())
        if len(self.history) > 50:
            self.history.pop(0)

    def undo(self) -> bool:
        if not self.history:
            return False
        snap = self.history.pop()
        self.restore(snap)
        return True

    # ------------------------------------------------------------
    #  Проверки
    # ------------------------------------------------------------

    def can_stack_tableau(self, card: tuple, on_card: tuple) -> bool:
        """Можно ли положить card на on_card (в колонке)."""
        if card is None or on_card is None:
            return False
        # Цвета должны различаться, ранги — по убыванию
        if is_red(card) == is_red(on_card):
            return False
        return card[1] == on_card[1] - 1

    def can_stack_foundation(self, card: tuple, foundation: list) -> bool:
        """Можно ли положить card в home."""
        if card is None:
            return False
        if not foundation:
            return card[1] == 0   # только Ace
        top = foundation[-1]
        return top[0] == card[0] and card[1] == top[1] + 1

    def foundation_index_for(self, card: tuple) -> int:
        """Какой home соответствует масти карты."""
        for i, suit in enumerate(SUITS):
            if suit == card[0]:
                return i
        return -1

    # ------------------------------------------------------------
    #  Ходы
    # ------------------------------------------------------------

    def draw_from_stock(self) -> bool:
        """Переворачивает одну карту из stock в waste. True если удалось."""
        if not self.stock:
            # Переворачиваем waste обратно в stock
            if not self.waste:
                return False
            self.push_history()
            self.stock = list(reversed(self.waste))
            self.waste = []
            self.recycle_count += 1
            self.score = max(0, self.score - 20)   # штраф
            return True
        self.push_history()
        card = self.stock.pop()
        self.waste.append(card)
        return True

    def can_move_to_foundation(self, card: tuple) -> bool:
        """Проверка — можно ли карту положить в её home."""
        idx = self.foundation_index_for(card)
        if idx < 0:
            return False
        return self.can_stack_foundation(card, self.foundations[idx])

    def move_to_foundation(self, card: tuple, source: str, col: int = -1) -> bool:
        """
        Пытается положить карту в home.
        source = 'waste' | 'tableau'
        """
        idx = self.foundation_index_for(card)
        if idx < 0:
            return False
        if not self.can_stack_foundation(card, self.foundations[idx]):
            return False

        self.push_history()

        if source == "waste":
            if not self.waste or self.waste[-1] != card:
                self.history.pop()
                return False
            self.waste.pop()
        elif source == "tableau":
            col_cards = self.tableau[col]
            if not col_cards or col_cards[-1] != card:
                self.history.pop()
                return False
            if not self.visible[col][-1]:
                self.history.pop()
                return False
            col_cards.pop()
            self.visible[col].pop()
            # Открываем новую верхнюю карту если есть
            if col_cards and not self.visible[col][-1]:
                self.visible[col][-1] = True
                self.score += 5
        else:
            self.history.pop()
            return False

        self.foundations[idx].append(card)
        self.score += 10
        self.moves += 1
        self.check_win()
        return True

    def move_tableau_to_tableau(self, src_col: int, card_idx: int,
                                  dst_col: int) -> bool:
        """Перемещает последовательность карт из src_col в dst_col."""
        if src_col == dst_col:
            return False
        src_cards = self.tableau[src_col]
        if card_idx < 0 or card_idx >= len(src_cards):
            return False
        # Все карты от card_idx должны быть открыты
        for i in range(card_idx, len(src_cards)):
            if not self.visible[src_col][i]:
                return False

        moving = src_cards[card_idx:]
        bottom = moving[0]

        # Проверка: можно ли положить в dst
        if not self.tableau[dst_col]:
            # В пустую колонку — только King
            if bottom[1] != 12:
                return False
        else:
            top = self.tableau[dst_col][-1]
            if not self.visible[dst_col][-1]:
                return False
            if not self.can_stack_tableau(bottom, top):
                return False

        self.push_history()

        # Убираем из src
        del src_cards[card_idx:]
        del self.visible[src_col][card_idx:]

        # Открываем новую верхнюю в src если есть
        if src_cards and not self.visible[src_col][-1]:
            self.visible[src_col][-1] = True
            self.score += 5

        # Кладём в dst
        self.tableau[dst_col].extend(moving)
        self.visible[dst_col].extend([True] * len(moving))

        self.moves += 1
        return True

    def move_waste_to_tableau(self, dst_col: int) -> bool:
        if not self.waste:
            return False
        card = self.waste[-1]

        if not self.tableau[dst_col]:
            if card[1] != 12:
                return False
        else:
            top = self.tableau[dst_col][-1]
            if not self.visible[dst_col][-1]:
                return False
            if not self.can_stack_tableau(card, top):
                return False

        self.push_history()
        self.waste.pop()
        self.tableau[dst_col].append(card)
        self.visible[dst_col].append(True)
        self.moves += 1
        return True

    # ------------------------------------------------------------

    def check_win(self):
        if all(len(f) == 13 for f in self.foundations):
            self.won = True

    def auto_play_foundations(self) -> bool:
        """Автоматически открывает все карты, которые можно положить в home."""
        moved_any = False
        changed = True
        while changed:
            changed = False
            # Из waste
            if self.waste and self.can_move_to_foundation(self.waste[-1]):
                if self.move_to_foundation(self.waste[-1], "waste"):
                    moved_any = True
                    changed = True
            # Из tableau (сверху)
            for c in range(7):
                if self.tableau[c] and self.visible[c][-1]:
                    card = self.tableau[c][-1]
                    if self.can_move_to_foundation(card):
                        if self.move_to_foundation(card, "tableau", c):
                            moved_any = True
                            changed = True
        return moved_any


# ============================================================
#  Виджет поля
# ============================================================

class SolitaireWidget(QWidget):
    """Отрисовка и взаимодействие."""

    game_changed = Signal()
    game_won = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.StrongFocus)
        self.game = SolitaireGame()

        # Для drag&drop
        self.dragging = None      # {"cards": [...], "src": ..., "col": ..., "idx": ..., "offset": QPoint}
        self.drag_pos = QPoint()

        # Размеры
        self._resize()

    def _resize(self):
        # 7 колонок + 4 дома + stock (11 колонок ширины) но у нас 7 колонок
        width = 7 * CARD_W + 8 * GAP
        height = 8 * (CARD_H + STACK_OFFSET) + GAP * 5
        self.setMinimumSize(width, height)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def new_game(self):
        self.game.new_game()
        self.dragging = None
        self.update()
        self.game_changed.emit()

    # ------------------------------------------------------------

    def _foundation_x(self, i: int) -> float:
        return GAP + i * (CARD_W + GAP)

    def _tableau_x(self, c: int) -> float:
        return GAP + c * (CARD_W + GAP)

    def _foundation_y(self) -> float:
        return GAP

    def _tableau_y(self) -> float:
        return GAP + CARD_H + GAP * 2

    def _stock_x(self) -> float:
        return self.width() - GAP - CARD_W

    def _stock_y(self) -> float:
        return GAP

    def _waste_x(self) -> float:
        return self.width() - GAP * 2 - CARD_W * 2

    def _waste_y(self) -> float:
        return GAP

    # ------------------------------------------------------------

    def _card_rect_tableau(self, col: int, idx: int) -> QRectF:
        """Прямоугольник карты в колонке."""
        x = self._tableau_x(col)
        y = self._tableau_y()
        for i in range(idx):
            if self.game.visible[col][i]:
                y += STACK_OFFSET
            else:
                y += FACEDOWN_OFFSET
        return QRectF(x, y, CARD_W, CARD_H)

    # ------------------------------------------------------------

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        # Фон
        grad = QLinearGradient(0, 0, 0, self.height())
        grad.setColorAt(0, QColor("#0A2A1A"))
        grad.setColorAt(1, QColor("#051510"))
        p.fillRect(self.rect(), QBrush(grad))

        # Места для домов
        for i in range(4):
            x = self._foundation_x(i)
            y = self._foundation_y()
            self._draw_empty_slot(p, x, y, "A" if not self.game.foundations[i]
                                              else "")

        # Дома
        for i, foundation in enumerate(self.game.foundations):
            x = self._foundation_x(i)
            y = self._foundation_y()
            if foundation:
                self._draw_card(p, foundation[-1], x, y, True)

        # Stock
        stock_x = self._stock_x()
        stock_y = self._stock_y()
        if self.game.stock:
            self._draw_card_back(p, stock_x, stock_y)
        else:
            self._draw_empty_slot(p, stock_x, stock_y, "↻")

        # Waste
        waste_x = self._waste_x()
        waste_y = self._waste_y()
        if self.game.waste:
            # Показываем до 3 карт
            for offset, card in enumerate(self.game.waste[-3:]):
                self._draw_card(p, card, waste_x + offset * 20, waste_y, True)

        # Tableau
        for col in range(7):
            for idx in range(len(self.game.tableau[col])):
                card = self.game.tableau[col][idx]
                rect = self._card_rect_tableau(col, idx)
                visible = self.game.visible[col][idx]

                # Если это часть перетаскиваемой группы — пропускаем
                if self.dragging:
                    if (self.dragging["src"] == "tableau" and
                        self.dragging["col"] == col and
                        idx >= self.dragging["idx"]):
                        continue

                if visible:
                    self._draw_card(p, card, rect.x(), rect.y(), True)
                else:
                    self._draw_card_back(p, rect.x(), rect.y())

        # Перетаскиваемая группа — поверх всего
        if self.dragging:
            offset = self.drag_pos
            for i, card in enumerate(self.dragging["cards"]):
                self._draw_card(
                    p, card,
                    offset.x(),
                    offset.y() + i * STACK_OFFSET,
                    True)

    def _draw_empty_slot(self, p: QPainter, x: float, y: float, label: str = ""):
        rect = QRectF(x, y, CARD_W, CARD_H)
        p.setBrush(QBrush(QColor(255, 255, 255, 20)))
        p.setPen(QPen(QColor(255, 255, 255, 60), 2, Qt.DashLine))
        p.drawRoundedRect(rect, 8, 8)

        if label:
            p.setPen(QColor(255, 255, 255, 100))
            font = QFont()
            font.setPointSize(28)
            p.setFont(font)
            p.drawText(rect, Qt.AlignCenter, label)

    def _draw_card(self, p: QPainter, card: tuple, x: float, y: float, face_up: bool):
        rect = QRectF(x, y, CARD_W, CARD_H)

        if not face_up:
            self._draw_card_back(p, x, y)
            return

        # Тень
        shadow = QRectF(x + 3, y + 3, CARD_W, CARD_H)
        p.setBrush(QBrush(QColor(0, 0, 0, 80)))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(shadow, 8, 8)

        # Фон карты
        grad = QLinearGradient(0, y, 0, y + CARD_H)
        grad.setColorAt(0, QColor("#FFFFFF"))
        grad.setColorAt(1, QColor("#F0F0F5"))
        p.setBrush(QBrush(grad))
        p.setPen(QPen(QColor(180, 180, 190), 1))
        p.drawRoundedRect(rect, 8, 8)

        # Масть и ранг
        suit, rank_idx = card
        rank = RANKS[rank_idx]
        color = RED if is_red(card) else BLACK

        # Верхний левый угол
        p.setPen(color)
        font = QFont()
        font.setPointSize(16)
        font.setBold(True)
        p.setFont(font)
        p.drawText(QRectF(x + 6, y + 4, CARD_W / 2, 24),
                   Qt.AlignLeft, rank)
        font.setPointSize(14)
        p.setFont(font)
        p.drawText(QRectF(x + 6, y + 22, CARD_W / 2, 22),
                   Qt.AlignLeft, suit)

        # Центральная масть (большая)
        font = QFont()
        font.setPointSize(34)
        p.setFont(font)
        p.setPen(color)
        p.drawText(QRectF(x, y + 40, CARD_W, CARD_H - 60),
                   Qt.AlignCenter, suit)

        # Нижний правый (перевёрнутый)
        p.save()
        p.translate(x + CARD_W - 6, y + CARD_H - 4)
        p.rotate(180)
        font.setPointSize(16)
        font.setBold(True)
        p.setFont(font)
        p.setPen(color)
        p.drawText(QRectF(-CARD_W/2, -24, CARD_W/2, 24),
                   Qt.AlignLeft, rank)
        font.setPointSize(14)
        p.setFont(font)
        p.drawText(QRectF(-CARD_W/2, -44, CARD_W/2, 22),
                   Qt.AlignLeft, suit)
        p.restore()

    def _draw_card_back(self, p: QPainter, x: float, y: float):
        rect = QRectF(x, y, CARD_W, CARD_H)

        # Тень
        shadow = QRectF(x + 3, y + 3, CARD_W, CARD_H)
        p.setBrush(QBrush(QColor(0, 0, 0, 80)))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(shadow, 8, 8)

        # Фон
        grad = QLinearGradient(0, y, 0, y + CARD_H)
        grad.setColorAt(0, QColor("#2E4A7A"))
        grad.setColorAt(1, QColor("#1A2A4A"))
        p.setBrush(QBrush(grad))
        p.setPen(QPen(QColor("#4060A0"), 2))
        p.drawRoundedRect(rect, 8, 8)

        # Узор
        inner = rect.adjusted(8, 8, -8, -8)
        p.setPen(QPen(QColor(255, 255, 255, 40), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(inner, 4, 4)

        # Ромбики
        p.setPen(QPen(QColor(255, 255, 255, 30), 1))
        for row in range(4):
            for col in range(3):
                cx = inner.left() + (col + 0.5) * inner.width() / 3
                cy = inner.top() + (row + 0.5) * inner.height() / 4
                size = 8
                diamond = QPolygonF([
                    QPointF(cx, cy - size),
                    QPointF(cx + size, cy),
                    QPointF(cx, cy + size),
                    QPointF(cx - size, cy),
                ])
                p.drawPolygon(diamond)

    # ------------------------------------------------------------
    #  Мышь
    # ------------------------------------------------------------

    def _find_tableau_card(self, pos: QPointF) -> tuple:
        """Возвращает (col, idx) если попали в карту tableau."""
        # Идём по колонкам справа налево (верхние карты выше)
        for col in range(7):
            # Идём снизу вверх по картам
            for idx in range(len(self.game.tableau[col]) - 1, -1, -1):
                rect = self._card_rect_tableau(col, idx)
                if rect.contains(pos):
                    return (col, idx)
        return (-1, -1)

    def mousePressEvent(self, e):
        if e.button() != Qt.LeftButton:
            return
        pos = e.position()

        # Клик по stock
        stock_rect = QRectF(self._stock_x(), self._stock_y(), CARD_W, CARD_H)
        if stock_rect.contains(pos):
            self.game.draw_from_stock()
            self.update()
            self.game_changed.emit()
            return

        # Клик по waste
        waste_x = self._waste_x()
        waste_y = self._waste_y()
        if self.game.waste:
            last_card_offset = (len(self.game.waste[-3:]) - 1) * 20
            waste_rect = QRectF(waste_x + last_card_offset,
                                 waste_y, CARD_W, CARD_H)
            if waste_rect.contains(pos):
                # Пробуем в foundation
                card = self.game.waste[-1]
                if self.game.can_move_to_foundation(card):
                    self.game.move_to_foundation(card, "waste")
                    self.update()
                    self.game_changed.emit()
                    return
                # Иначе начинаем drag
                self.dragging = {
                    "cards": [card],
                    "src": "waste",
                    "col": -1,
                    "idx": -1,
                    "offset": pos - QPointF(waste_x + last_card_offset, waste_y),
                }
                self.drag_pos = QPointF(waste_x + last_card_offset, waste_y)
                return

        # Клик по tableau
        col, idx = self._find_tableau_card(pos)
        if col >= 0 and idx >= 0:
            if not self.game.visible[col][idx]:
                return
            # Если это верхняя карта — пробуем автоход в foundation
            if idx == len(self.game.tableau[col]) - 1:
                card = self.game.tableau[col][-1]
                if self.game.can_move_to_foundation(card):
                    self.game.move_to_foundation(card, "tableau", col)
                    self.update()
                    self.game_changed.emit()
                    return
            # Иначе — drag всей последовательности
            cards = self.game.tableau[col][idx:]
            rect = self._card_rect_tableau(col, idx)
            self.dragging = {
                "cards": list(cards),
                "src": "tableau",
                "col": col,
                "idx": idx,
                "offset": pos - rect.topLeft(),
            }
            self.drag_pos = rect.topLeft()
            return

    def mouseMoveEvent(self, e):
        if self.dragging and e.buttons() & Qt.LeftButton:
            self.drag_pos = e.position() - self.dragging["offset"]
            self.update()

    def mouseReleaseEvent(self, e):
        if not self.dragging:
            return
        pos = e.position()
        dragging = self.dragging
        self.dragging = None

        # Куда отпустили?
        # Проверяем foundation (для одиночной карты)
        if len(dragging["cards"]) == 1:
            card = dragging["cards"][0]
            for i in range(4):
                fx = self._foundation_x(i)
                fy = self._foundation_y()
                rect = QRectF(fx, fy, CARD_W, CARD_H)
                if rect.intersects(QRectF(pos.x() - CARD_W/2,
                                            pos.y() - CARD_H/2,
                                            CARD_W, CARD_H)):
                    # Проверим что это правильная масть
                    if self.game.foundation_index_for(card) == i:
                        if dragging["src"] == "waste":
                            # Возвращаем в waste для корректного хода
                            # (у нас не pop из waste)
                            if self.game.waste and self.game.waste[-1] == card:
                                self.game.move_to_foundation(card, "waste")
                                self.update()
                                self.game_changed.emit()
                                return
                        elif dragging["src"] == "tableau":
                            col = dragging["col"]
                            if (self.game.tableau[col] and
                                self.game.tableau[col][-1] == card):
                                self.game.move_to_foundation(card, "tableau", col)
                                self.update()
                                self.game_changed.emit()
                                return

        # Проверяем tableau
        target_col = -1
        best_dist = 99999
        for c in range(7):
            cx = self._tableau_x(c) + CARD_W / 2
            # Ищем ближайшую колонку по X
            dist = abs(pos.x() - cx)
            if dist < best_dist and dist < CARD_W:
                best_dist = dist
                target_col = c

        if target_col >= 0:
            if dragging["src"] == "waste":
                if self.game.move_waste_to_tableau(target_col):
                    self.update()
                    self.game_changed.emit()
                    return
            elif dragging["src"] == "tableau":
                if self.game.move_tableau_to_tableau(
                        dragging["col"], dragging["idx"], target_col):
                    self.update()
                    self.game_changed.emit()
                    return

        # Ничего не подошло — вернуть на место
        self.update()

    def mouseDoubleClickEvent(self, e):
        if e.button() != Qt.LeftButton:
            return
        pos = e.position()

        # Клик по колонке — автоход верхней карты в foundation
        col, idx = self._find_tableau_card(pos)
        if col >= 0 and idx == len(self.game.tableau[col]) - 1:
            card = self.game.tableau[col][-1]
            if self.game.can_move_to_foundation(card):
                self.game.move_to_foundation(card, "tableau", col)
                self.update()
                self.game_changed.emit()
                return

        # Клик по waste — тоже автоход
        waste_x = self._waste_x()
        waste_y = self._waste_y()
        if self.game.waste:
            last_card_offset = (len(self.game.waste[-3:]) - 1) * 20
            waste_rect = QRectF(waste_x + last_card_offset, waste_y,
                                 CARD_W, CARD_H)
            if waste_rect.contains(pos):
                card = self.game.waste[-1]
                if self.game.can_move_to_foundation(card):
                    self.game.move_to_foundation(card, "waste")
                    self.update()
                    self.game_changed.emit()
                    return

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_U and e.modifiers() & Qt.ControlModifier:
            if self.game.undo():
                self.update()
                self.game_changed.emit()
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

    st = {
        "start_time": 0.0,
        "timer_running": False,
        "elapsed": 0,
        "records": {},
        "won_shown": False,
    }

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
    ll.setContentsMargins(24, 24, 24, 24)
    ll.setSpacing(14)

    board = SolitaireWidget()
    ll.addWidget(board, 1)

    hint = QLabel("Тащи карты мышью · Двойной клик — в дом · "
                   "Клик по колоде — перевернуть · Ctrl+Z — отмена")
    hint.setAlignment(Qt.AlignCenter)
    hint.setStyleSheet("color: rgba(255,255,255,0.45); font-size: 11px;")
    ll.addWidget(hint)

    h.addWidget(left, 1)

    # ---- Правая панель ----
    right = QWidget()
    right.setFixedWidth(260)
    right.setStyleSheet("""
        background: rgba(255,255,255,0.04);
        border-left: 1px solid rgba(255,255,255,0.08);
    """)
    rl = QVBoxLayout(right)
    rl.setContentsMargins(20, 24, 20, 24)
    rl.setSpacing(14)

    title = QLabel("🃏  Косынка")
    title.setStyleSheet("color: white; font-size: 20px; font-weight: 600; padding: 2px;")
    rl.addWidget(title)

    hint2 = QLabel("Собери все карты в 4 дома.\n"
                    "Дом — по масти, от Ace до King.")
    hint2.setStyleSheet("color: rgba(255,255,255,0.55); font-size: 12px;")
    hint2.setWordWrap(True)
    rl.addWidget(hint2)

    rl.addSpacing(10)

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

    score_box, score_val = make_metric("СЧЁТ", "star", "110,198,255")
    rl.addWidget(score_box)

    moves_box, moves_val = make_metric("ХОДОВ", "grid", "110,231,183")
    rl.addWidget(moves_box)

    time_box, time_val = make_metric("ВРЕМЯ", "clock", "255,184,108")
    rl.addWidget(time_box)

    rl.addSpacing(10)

    # Рекорд
    rec_lbl = QLabel("ЛУЧШИЙ РЕЗУЛЬТАТ")
    rec_lbl.setStyleSheet("""
        color: rgba(255,255,255,0.45);
        font-size: 10px;
        font-weight: 700;
        letter-spacing: 1.5px;
    """)
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

    best_score_lbl = QLabel("— очков")
    best_score_lbl.setStyleSheet("""
        color: #FFB86C;
        font-size: 14px;
        font-weight: 600;
        background: transparent;
        border: none;
    """)
    rbl.addWidget(best_score_lbl)

    best_time_lbl = QLabel("")
    best_time_lbl.setStyleSheet("""
        color: rgba(255,255,255,0.55);
        font-size: 11px;
        background: transparent;
        border: none;
    """)
    rbl.addWidget(best_time_lbl)

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

    auto_btn = QPushButton("⚡  Автоход в дома")
    auto_btn.setCursor(Qt.PointingHandCursor)
    auto_btn.setFixedHeight(38)
    auto_btn.setStyleSheet("""
        QPushButton {
            background: rgba(110,231,183,0.18);
            color: #6EE7B7;
            border: 1px solid rgba(110,231,183,0.45);
            border-radius: 10px;
            font-size: 12px;
        }
        QPushButton:hover { background: rgba(110,231,183,0.35); color: white; }
    """)
    rl.addWidget(auto_btn)

    h.addWidget(right)

    # ============================================================
    #  Логика
    # ============================================================

    timer = QTimer(root)
    timer.setInterval(1000)

    def update_metrics():
        if st["timer_running"]:
            st["elapsed"] = int(time.time() - st["start_time"])
        score_val.setText(str(board.game.score))
        moves_val.setText(str(board.game.moves))
        m = st["elapsed"] // 60
        s = st["elapsed"] % 60
        time_val.setText(f"{m:02d}:{s:02d}")

    def on_tick():
        if st["timer_running"]:
            update_metrics()

    timer.timeout.connect(on_tick)

    def refresh_records():
        rec = st["records"]
        if rec.get("score"):
            best_score_lbl.setText(f"{rec['score']} очков")
            t = rec.get("time", 0)
            m = t // 60
            s = t % 60
            best_time_lbl.setText(f"{m:02d}:{s:02d}")
        else:
            best_score_lbl.setText("— очков")
            best_time_lbl.setText("")

    def save_game():
        if vfs is None:
            return
        try:
            vfs.mkdir("/Documents")
            data = {
                "tableau": board.game.tableau,
                "foundations": board.game.foundations,
                "stock": board.game.stock,
                "waste": board.game.waste,
                "visible": board.game.visible,
                "moves": board.game.moves,
                "score": board.game.score,
                "elapsed": st["elapsed"],
                "saved_at": time.time(),
            }
            vfs.write_text(SAVE_PATH,
                json.dumps(data, ensure_ascii=False, indent=2))
        except Exception as e:
            print(f"[Solitaire] save: {e}")

    def load_game() -> bool:
        if vfs is None:
            return False
        try:
            raw = vfs.read_text(SAVE_PATH, "")
            if not raw.strip():
                return False
            data = json.loads(raw)
            # Восстанавливаем
            board.game.tableau = [list(col) for col in data["tableau"]]
            # Преобразуем карты из списков в кортежи
            for col in range(7):
                board.game.tableau[col] = [tuple(c) for c in board.game.tableau[col]]
            board.game.foundations = [[tuple(c) for c in f]
                                        for f in data["foundations"]]
            board.game.stock = [tuple(c) for c in data["stock"]]
            board.game.waste = [tuple(c) for c in data["waste"]]
            board.game.visible = [list(v) for v in data["visible"]]
            board.game.moves = data.get("moves", 0)
            board.game.score = data.get("score", 0)

            st["elapsed"] = data.get("elapsed", 0)
            st["start_time"] = time.time() - st["elapsed"]
            st["timer_running"] = True
            timer.start()
            update_metrics()
            board.update()
            return True
        except Exception as e:
            print(f"[Solitaire] load: {e}")
            return False

    def new_game():
        timer.stop()
        st["timer_running"] = False
        st["elapsed"] = 0
        st["won_shown"] = False
        board.new_game()
        st["start_time"] = time.time()
        st["timer_running"] = True
        timer.start()
        update_metrics()

    def on_game_changed():
        update_metrics()
        save_game()
        # Проверка победы
        if board.game.won and not st["won_shown"]:
            st["won_shown"] = True
            QTimer.singleShot(300, on_win)

    def on_win():
        timer.stop()
        st["timer_running"] = False
        score = board.game.score
        moves = board.game.moves
        elapsed = st["elapsed"]

        # Рекорд
        cur = st["records"]
        new_record = False
        if score > cur.get("score", 0):
            new_record = True
        elif score == cur.get("score", 0) and elapsed < cur.get("time", 99999):
            new_record = True

        if new_record:
            st["records"] = {
                "score": score,
                "moves": moves,
                "time": elapsed,
                "date": datetime.now().isoformat(),
            }
            save_records()
            refresh_records()

        m = elapsed // 60
        s = elapsed % 60

        if desktop and hasattr(desktop, "notifications"):
            desktop.notifications.push(
                "🃏 Косынка разложена!",
                f"Счёт: {score}, ходов: {moves}, время: {m:02d}:{s:02d}"
                + ("  (новый рекорд!)" if new_record else ""))

        QMessageBox.information(root, "🏆 Победа!",
            f"Пасьянс разложен!\n\n"
            f"Счёт: {score}\n"
            f"Ходов: {moves}\n"
            f"Время: {m:02d}:{s:02d}\n"
            f"{'🏆 Новый рекорд!' if new_record else ''}")

    def undo():
        if board.game.undo():
            board.update()
            update_metrics()
            save_game()

    def auto_play():
        if board.game.auto_play_foundations():
            board.update()
            update_metrics()
            save_game()

    board.game_changed.connect(on_game_changed)
    new_btn.clicked.connect(new_game)
    undo_btn.clicked.connect(undo)
    auto_btn.clicked.connect(auto_play)

    # Автосохранение
    autosave = QTimer(root)
    autosave.setInterval(5000)
    autosave.timeout.connect(save_game)
    autosave.start()

    # Старт
    if not load_game():
        new_game()
    else:
        update_metrics()

    refresh_records()
    QTimer.singleShot(200, board.setFocus)

    return root