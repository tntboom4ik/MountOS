"""
MountOS — Карточки-повторение (Flashcards).

Anki-подобное приложение для запоминания:
  • Колоды карточек (создание/редактирование/удаление)
  • Формат: вопрос — ответ
  • Интервальное повторение (SM-2 — как в Anki)
  • 3 оценки ответа: Забыл / Трудно / Легко
  • Статистика: сколько выучено, точность, streak
  • Импорт/экспорт колод в VFS (JSON)
  • Тренировка с прогрессом
  • Свои настройки интервалов

Установка: apps/flashcards.py + перезапуск MountOS.
"""

import json
import os
import random
import time
from datetime import datetime, date, timedelta

from PySide6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QLabel,
                                QPushButton, QLineEdit, QListWidget,
                                QListWidgetItem, QTextEdit, QComboBox,
                                QMessageBox, QInputDialog, QScrollArea,
                                QFrame, QDialog, QDialogButtonBox, QFormLayout,
                                QSizePolicy, QStackedWidget, QProgressBar)
from PySide6.QtCore import Qt, QTimer, Signal, QSize
from PySide6.QtGui import (QFont, QIcon, QColor, QPainter, QPainterPath,
                            QBrush, QPen)

from ui.icons import get_icon
from ui.settings_state import state
from ui.context_menu import make_menu

APP_NAME = "Карточки"
APP_ICON = "editor"
APP_VERSION = "1.0"
APP_AUTHOR = "MountOS"


DECKS_PATH = "/Notes/flashcards_decks.json"
STATS_PATH = "/Notes/flashcards_stats.json"


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
#  SM-2 алгоритм интервального повторения
# ============================================================

class Card:
    """
    Одна карточка.
    Хранит состояние для SM-2:
      - interval: текущий интервал в днях
      - easiness: коэффициент лёгкости (2.5 по умолчанию)
      - reps: число успешных повторений
      - due: timestamp следующего показа
      - last_review: timestamp последнего показа
    """

    def __init__(self, question: str = "", answer: str = "",
                 hint: str = ""):
        self.question = question
        self.answer = answer
        self.hint = hint

        # SM-2 state
        self.interval = 0            # в днях
        self.easiness = 2.5          # коэффициент
        self.reps = 0                # число успешных повторений
        self.lapses = 0              # сколько раз забыл
        self.due = time.time()       # когда показать
        self.last_review = 0
        self.total_reviews = 0
        self.correct_reviews = 0

    def is_due(self) -> bool:
        return self.due <= time.time()

    def review(self, quality: int):
        """
        Оценка ответа: 0=Забыл, 3=Трудно, 5=Легко.
        Обновляет интервал по SM-2.
        """
        self.total_reviews += 1
        self.last_review = time.time()

        if quality < 3:
            # Забыл — сброс
            self.reps = 0
            self.lapses += 1
            self.interval = 1  # повторить завтра
        else:
            self.correct_reviews += 1
            if self.reps == 0:
                self.interval = 1
            elif self.reps == 1:
                self.interval = 6
            else:
                self.interval = round(self.interval * self.easiness)
            self.reps += 1

        # Обновляем easiness
        self.easiness = max(1.3,
            self.easiness + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02)))

        # Следующая дата
        self.due = time.time() + self.interval * 86400

    def to_dict(self) -> dict:
        return {
            "question": self.question,
            "answer": self.answer,
            "hint": self.hint,
            "interval": self.interval,
            "easiness": self.easiness,
            "reps": self.reps,
            "lapses": self.lapses,
            "due": self.due,
            "last_review": self.last_review,
            "total_reviews": self.total_reviews,
            "correct_reviews": self.correct_reviews,
        }

    @classmethod
    def from_dict(cls, d: dict):
        c = cls(d.get("question", ""), d.get("answer", ""), d.get("hint", ""))
        c.interval = d.get("interval", 0)
        c.easiness = d.get("easiness", 2.5)
        c.reps = d.get("reps", 0)
        c.lapses = d.get("lapses", 0)
        c.due = d.get("due", time.time())
        c.last_review = d.get("last_review", 0)
        c.total_reviews = d.get("total_reviews", 0)
        c.correct_reviews = d.get("correct_reviews", 0)
        return c


class Deck:
    """Колода карточек."""

    def __init__(self, name: str = ""):
        self.name = name
        self.cards = []  # список Card
        self.created = time.time()

    def due_cards(self) -> list:
        """Карточки, которые пора повторить."""
        return [c for c in self.cards if c.is_due()]

    def new_cards(self) -> list:
        """Карточки, которые ни разу не показывали."""
        return [c for c in self.cards if c.total_reviews == 0]

    def stats(self) -> dict:
        total = len(self.cards)
        due = len(self.due_cards())
        new = len(self.new_cards())
        learned = sum(1 for c in self.cards
                       if c.interval >= 21 and c.total_reviews > 0)
        review = total - new
        total_reviews = sum(c.total_reviews for c in self.cards)
        correct = sum(c.correct_reviews for c in self.cards)
        accuracy = (correct / total_reviews * 100) if total_reviews else 0
        return {
            "total": total,
            "due": due,
            "new": new,
            "review": review,
            "learned": learned,
            "accuracy": accuracy,
            "total_reviews": total_reviews,
        }

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "created": self.created,
            "cards": [c.to_dict() for c in self.cards],
        }

    @classmethod
    def from_dict(cls, d: dict):
        deck = cls(d.get("name", ""))
        deck.created = d.get("created", time.time())
        deck.cards = [Card.from_dict(cd) for cd in d.get("cards", [])]
        return deck


# ============================================================
#  Диалог редактирования карточки
# ============================================================

class CardEditDialog(QDialog):
    def __init__(self, card: Card = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Карточка")
        self.resize(520, 400)
        self.setStyleSheet("""
            QDialog { background: #1A1F35; }
            QLabel { color: white; font-size: 12px; }
            QLineEdit, QTextEdit {
                background: rgba(255,255,255,0.08);
                color: white;
                border: 1px solid rgba(255,255,255,0.15);
                border-radius: 8px;
                padding: 8px 10px;
                font-size: 13px;
            }
            QLineEdit:focus, QTextEdit:focus {
                border: 1px solid rgba(110,198,255,0.6);
            }
        """)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(12)

        lay.addWidget(QLabel("Вопрос:"))
        self.q_input = QTextEdit()
        self.q_input.setFixedHeight(80)
        self.q_input.setPlaceholderText("Что нужно вспомнить?")
        lay.addWidget(self.q_input)

        lay.addWidget(QLabel("Ответ:"))
        self.a_input = QTextEdit()
        self.a_input.setFixedHeight(80)
        self.a_input.setPlaceholderText("Правильный ответ")
        lay.addWidget(self.a_input)

        lay.addWidget(QLabel("Подсказка (необязательно):"))
        self.h_input = QLineEdit()
        self.h_input.setPlaceholderText("Например, первая буква")
        lay.addWidget(self.h_input)

        # Кнопки
        btns = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        btns.setStyleSheet("""
            QPushButton {
                background: rgba(110,198,255,0.20);
                color: white;
                border: 1px solid rgba(110,198,255,0.50);
                border-radius: 8px;
                padding: 8px 16px;
                font-size: 12px;
                min-width: 80px;
            }
            QPushButton:hover { background: rgba(110,198,255,0.40); }
        """)
        lay.addWidget(btns)

        if card:
            self.q_input.setPlainText(card.question)
            self.a_input.setPlainText(card.answer)
            self.h_input.setText(card.hint)

    def get_data(self) -> dict:
        return {
            "question": self.q_input.toPlainText().strip(),
            "answer": self.a_input.toPlainText().strip(),
            "hint": self.h_input.text().strip(),
        }


# ============================================================
#  Виджет тренировки
# ============================================================

class TrainingView(QWidget):
    """Режим тренировки."""

    finished = Signal(dict)   # статистика сессии

    def __init__(self, parent=None):
        super().__init__(parent)
        self.deck = None
        self.queue = []          # очередь карт на показ
        self.current = None      # текущая карта
        self.answered = False    # показан ли ответ
        self.session_stats = {
            "total": 0,
            "forgot": 0,
            "hard": 0,
            "easy": 0,
            "started": 0,
        }

        self._build_ui()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(40, 30, 40, 30)
        lay.setSpacing(20)

        # Верхняя строка со статистикой
        top = QHBoxLayout()
        top.setSpacing(20)

        self.deck_lbl = QLabel("—")
        self.deck_lbl.setStyleSheet("color: white; font-size: 16px; font-weight: 600;")
        top.addWidget(self.deck_lbl)

        top.addStretch(1)

        self.counter_lbl = QLabel("0 / 0")
        self.counter_lbl.setStyleSheet("""
            color: rgba(255,255,255,0.55);
            font-size: 13px;
            font-family: Consolas, monospace;
        """)
        top.addWidget(self.counter_lbl)

        lay.addLayout(top)

        # Прогресс
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(6)
        self.progress.setStyleSheet("""
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
        lay.addWidget(self.progress)

        lay.addSpacing(20)

        # Карточка
        self.card_widget = QWidget()
        self.card_widget.setStyleSheet("""
            QWidget {
                background: rgba(255,255,255,0.06);
                border: 1px solid rgba(255,255,255,0.12);
                border-radius: 20px;
            }
        """)
        cl = QVBoxLayout(self.card_widget)
        cl.setContentsMargins(40, 40, 40, 40)
        cl.setSpacing(20)

        self.card_type_lbl = QLabel("ВОПРОС")
        self.card_type_lbl.setAlignment(Qt.AlignCenter)
        self.card_type_lbl.setStyleSheet("""
            color: rgba(255,255,255,0.45);
            font-size: 11px;
            font-weight: 700;
            letter-spacing: 3px;
            background: transparent;
            border: none;
        """)
        cl.addWidget(self.card_type_lbl)

        self.question_lbl = QLabel("")
        self.question_lbl.setAlignment(Qt.AlignCenter)
        self.question_lbl.setWordWrap(True)
        self.question_lbl.setStyleSheet("""
            color: white;
            font-size: 24px;
            font-weight: 300;
            background: transparent;
            border: none;
            padding: 10px;
        """)
        cl.addWidget(self.question_lbl, 1)

        # Подсказка
        self.hint_lbl = QLabel("")
        self.hint_lbl.setAlignment(Qt.AlignCenter)
        self.hint_lbl.setStyleSheet("""
            color: rgba(255,255,255,0.55);
            font-size: 13px;
            font-style: italic;
            background: transparent;
            border: none;
        """)
        self.hint_lbl.hide()
        cl.addWidget(self.hint_lbl)

        # Ответ
        self.answer_lbl = QLabel("")
        self.answer_lbl.setAlignment(Qt.AlignCenter)
        self.answer_lbl.setWordWrap(True)
        self.answer_lbl.setStyleSheet("""
            color: #6EC6FF;
            font-size: 22px;
            font-weight: 600;
            background: transparent;
            border: none;
            padding: 10px;
        """)
        self.answer_lbl.hide()
        cl.addWidget(self.answer_lbl, 1)

        lay.addWidget(self.card_widget, 1)

        # Кнопки показать / оценить
        self.show_answer_btn = QPushButton("👁  Показать ответ")
        self.show_answer_btn.setCursor(Qt.PointingHandCursor)
        self.show_answer_btn.setFixedHeight(52)
        self.show_answer_btn.setStyleSheet("""
            QPushButton {
                background: rgba(110,198,255,0.25);
                color: white;
                border: 1px solid rgba(110,198,255,0.60);
                border-radius: 12px;
                font-size: 15px;
                font-weight: 600;
            }
            QPushButton:hover { background: rgba(110,198,255,0.45); }
        """)
        self.show_answer_btn.clicked.connect(self.show_answer)
        lay.addWidget(self.show_answer_btn)

        # Панель оценки (скрыта до показа ответа)
        self.rating_widget = QWidget()
        rating_row = QHBoxLayout(self.rating_widget)
        rating_row.setContentsMargins(0, 0, 0, 0)
        rating_row.setSpacing(12)

        def make_rating_btn(text: str, tooltip: str, color: str, quality: int):
            b = QPushButton(text)
            b.setCursor(Qt.PointingHandCursor)
            b.setFixedHeight(56)
            b.setToolTip(tooltip)
            b.setStyleSheet(f"""
                QPushButton {{
                    background: rgba({color}, 0.20);
                    color: white;
                    border: 1px solid rgba({color}, 0.60);
                    border-radius: 12px;
                    font-size: 14px;
                    font-weight: 600;
                }}
                QPushButton:hover {{
                    background: rgba({color}, 0.40);
                }}
            """)
            b.clicked.connect(lambda: self.rate(quality))
            return b

        rating_row.addWidget(make_rating_btn(
            "🔴  Забыл", "Повторить завтра", "255,107,138", 0))
        rating_row.addWidget(make_rating_btn(
            "🟠  Трудно", "Увеличить интервал чуть-чуть", "255,184,108", 3))
        rating_row.addWidget(make_rating_btn(
            "🟢  Легко", "Большой интервал", "110,231,183", 5))

        self.rating_widget.hide()
        lay.addWidget(self.rating_widget)

        # Нижняя строка с прогрессом сессии
        self.session_lbl = QLabel("")
        self.session_lbl.setAlignment(Qt.AlignCenter)
        self.session_lbl.setStyleSheet("""
            color: rgba(255,255,255,0.55);
            font-size: 12px;
            background: transparent;
            border: none;
        """)
        lay.addWidget(self.session_lbl)

    # ------------------------------------------------------------

    def start(self, deck: Deck):
        """Начинает тренировку по колоде."""
        self.deck = deck
        self.session_stats = {
            "total": 0,
            "forgot": 0,
            "hard": 0,
            "easy": 0,
            "started": time.time(),
        }

        # Собираем очередь: сначала due, потом новые
        due = deck.due_cards()
        new = deck.new_cards()
        # Перемешиваем
        random.shuffle(due)
        random.shuffle(new)
        self.queue = due + new

        if not self.queue:
            self.deck_lbl.setText(f"📚  {deck.name}")
            self.question_lbl.setText("🎉  Всё повторено!\n\nНет карточек для повтора.")
            self.question_lbl.setStyleSheet("""
                color: #6EE7B7;
                font-size: 20px;
                font-weight: 400;
                background: transparent;
                border: none;
                padding: 10px;
            """)
            self.show_answer_btn.hide()
            self.rating_widget.hide()
            self.counter_lbl.setText("0 / 0")
            self.progress.setValue(100)
            return

        self.session_stats["total"] = len(self.queue)
        self.deck_lbl.setText(f"📚  {deck.name}")
        self.question_lbl.setStyleSheet("""
            color: white;
            font-size: 24px;
            font-weight: 300;
            background: transparent;
            border: none;
            padding: 10px;
        """)
        self.show_answer_btn.show()
        self._next_card()

    def _next_card(self):
        if not self.queue:
            self._finish()
            return
        self.current = self.queue.pop(0)
        self.answered = False

        # Показываем вопрос
        self.card_type_lbl.setText("ВОПРОС")
        self.question_lbl.setText(self.current.question)
        self.answer_lbl.hide()
        self.answer_lbl.setText("")

        # Подсказка
        if self.current.hint:
            self.hint_lbl.setText(f"💡 {self.current.hint}")
            self.hint_lbl.show()
        else:
            self.hint_lbl.hide()

        self.show_answer_btn.show()
        self.rating_widget.hide()

        # Прогресс
        done = self.session_stats["total"] - len(self.queue) - 1
        total = max(1, self.session_stats["total"])
        pct = int(done / total * 100)
        self.progress.setValue(pct)
        self.counter_lbl.setText(
            f"{done + 1} / {self.session_stats['total']}")

        self._update_session_label()

    def _update_session_label(self):
        s = self.session_stats
        answered = s["forgot"] + s["hard"] + s["easy"]
        if answered == 0:
            self.session_lbl.setText(
                f"Карточек: {s['total']}  ·  нажми «Показать ответ»")
        else:
            self.session_lbl.setText(
                f"Отвечено: {answered}  ·  "
                f"❌ {s['forgot']}  🟠 {s['hard']}  🟢 {s['easy']}")

    def show_answer(self):
        if self.current is None or self.answered:
            return
        self.answered = True
        self.card_type_lbl.setText("ОТВЕТ")
        self.question_lbl.setText(self.current.question)
        self.answer_lbl.setText(self.current.answer)
        self.answer_lbl.show()
        self.show_answer_btn.hide()
        self.rating_widget.show()

    def rate(self, quality: int):
        if self.current is None or not self.answered:
            return

        self.current.review(quality)

        if quality == 0:
            self.session_stats["forgot"] += 1
            # Вернуть в очередь через несколько карт
            self.queue.append(self.current)
        elif quality == 3:
            self.session_stats["hard"] += 1
        else:
            self.session_stats["easy"] += 1

        self._next_card()

    def _finish(self):
        self.progress.setValue(100)
        elapsed = int(time.time() - self.session_stats["started"])
        m = elapsed // 60
        s = elapsed % 60
        self.question_lbl.setText("🎉  Сессия завершена!")
        self.question_lbl.setStyleSheet("""
            color: #6EE7B7;
            font-size: 24px;
            font-weight: 400;
            background: transparent;
            border: none;
        """)
        self.answer_lbl.hide()
        self.hint_lbl.hide()
        self.show_answer_btn.hide()
        self.rating_widget.hide()
        self.session_lbl.setText(
            f"Время: {m:02d}:{s:02d}  ·  "
            f"❌ {self.session_stats['forgot']}  "
            f"🟠 {self.session_stats['hard']}  "
            f"🟢 {self.session_stats['easy']}")

        self.finished.emit(self.session_stats)


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
        "decks": [],       # список Deck
        "current_deck": None,
        "view": "list",    # "list" | "cards" | "training"
    }

    # ---- Загрузка колод ----
    if vfs:
        try:
            raw = vfs.read_text(DECKS_PATH, "")
            if raw.strip():
                data = json.loads(raw)
                st["decks"] = [Deck.from_dict(d) for d in data]
        except Exception as e:
            print(f"[Flashcards] load decks: {e}")

    def save_decks():
        if vfs is None:
            return
        try:
            vfs.mkdir("/Notes")
            data = [d.to_dict() for d in st["decks"]]
            vfs.write_text(DECKS_PATH,
                json.dumps(data, ensure_ascii=False, indent=2))
        except Exception as e:
            print(f"[Flashcards] save decks: {e}")

    # ---- Левая панель — список колод ----
    side = QWidget()
    side.setFixedWidth(300)
    side.setStyleSheet("""
        background: rgba(255,255,255,0.04);
        border-right: 1px solid rgba(255,255,255,0.08);
    """)
    sl = QVBoxLayout(side)
    sl.setContentsMargins(14, 16, 14, 16)
    sl.setSpacing(10)

    title = QLabel("🎴  Карточки")
    title.setStyleSheet("color: white; font-size: 16px; font-weight: 600; padding: 2px;")
    sl.addWidget(title)

    add_deck_btn = QPushButton("＋  Новая колода")
    add_deck_btn.setCursor(Qt.PointingHandCursor)
    add_deck_btn.setFixedHeight(38)
    add_deck_btn.setStyleSheet("""
        QPushButton {
            background: rgba(110,198,255,0.22);
            color: white;
            border: 1px solid rgba(110,198,255,0.55);
            border-radius: 10px;
            font-size: 13px;
            font-weight: 600;
        }
        QPushButton:hover { background: rgba(110,198,255,0.42); }
    """)
    sl.addWidget(add_deck_btn)

    deck_list = QListWidget()
    deck_list.setStyleSheet("""
        QListWidget {
            background: rgba(0,0,0,0.20);
            color: white;
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 10px;
            padding: 4px;
            font-size: 12px;
            outline: none;
        }
        QListWidget::item {
            padding: 10px 12px;
            border-radius: 8px;
        }
        QListWidget::item:hover { background: rgba(255,255,255,0.08); }
        QListWidget::item:selected { background: rgba(110,198,255,0.30); }
    """)
    sl.addWidget(deck_list, 1)

    # Статистика колоды
    stats_box = QLabel()
    stats_box.setWordWrap(True)
    stats_box.setStyleSheet("""
        background: rgba(110,198,255,0.10);
        color: rgba(255,255,255,0.85);
        border: 1px solid rgba(110,198,255,0.30);
        border-radius: 10px;
        padding: 10px 12px;
        font-size: 11px;
    """)
    sl.addWidget(stats_box)

    h.addWidget(side)

    # ---- Правая часть — QStackedWidget ----
    right = QStackedWidget()

    # ============================================================
    #  Страница 1: карточки колоды
    # ============================================================
    cards_page = QWidget()
    cpl = QVBoxLayout(cards_page)
    cpl.setContentsMargins(30, 30, 30, 30)
    cpl.setSpacing(16)

    # Заголовок
    header = QHBoxLayout()
    deck_title_lbl = QLabel("Выбери колоду")
    deck_title_lbl.setStyleSheet("color: white; font-size: 22px; font-weight: 600;")
    header.addWidget(deck_title_lbl)
    header.addStretch(1)

    train_btn = QPushButton("🎯  Тренировка")
    train_btn.setCursor(Qt.PointingHandCursor)
    train_btn.setFixedHeight(42)
    train_btn.setStyleSheet("""
        QPushButton {
            background: rgba(110,231,183,0.25);
            color: white;
            border: 1px solid rgba(110,231,183,0.60);
            border-radius: 10px;
            padding: 8px 22px;
            font-size: 13px;
            font-weight: 600;
        }
        QPushButton:hover { background: rgba(110,231,183,0.45); }
        QPushButton:disabled {
            background: rgba(255,255,255,0.04);
            color: rgba(255,255,255,0.35);
            border: 1px solid rgba(255,255,255,0.08);
        }
    """)
    train_btn.setEnabled(False)
    header.addWidget(train_btn)

    add_card_btn = QPushButton("＋  Карточка")
    add_card_btn.setCursor(Qt.PointingHandCursor)
    add_card_btn.setFixedHeight(42)
    add_card_btn.setStyleSheet("""
        QPushButton {
            background: rgba(110,198,255,0.22);
            color: white;
            border: 1px solid rgba(110,198,255,0.55);
            border-radius: 10px;
            padding: 8px 22px;
            font-size: 13px;
            font-weight: 600;
        }
        QPushButton:hover { background: rgba(110,198,255,0.42); }
        QPushButton:disabled {
            background: rgba(255,255,255,0.04);
            color: rgba(255,255,255,0.35);
            border: 1px solid rgba(255,255,255,0.08);
        }
    """)
    add_card_btn.setEnabled(False)
    header.addWidget(add_card_btn)

    cpl.addLayout(header)

    # Список карточек
    cards_list = QListWidget()
    cards_list.setStyleSheet("""
        QListWidget {
            background: rgba(0,0,0,0.20);
            color: white;
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 12px;
            padding: 6px;
            font-size: 13px;
            outline: none;
        }
        QListWidget::item {
            padding: 12px 14px;
            border-radius: 8px;
            border: 1px solid transparent;
        }
        QListWidget::item:hover { background: rgba(255,255,255,0.08); }
        QListWidget::item:selected {
            background: rgba(110,198,255,0.25);
            border: 1px solid rgba(110,198,255,0.50);
        }
    """)
    cpl.addWidget(cards_list, 1)

    right.addWidget(cards_page)

    # ============================================================
    #  Страница 2: тренировка
    # ============================================================
    training_view = TrainingView()
    right.addWidget(training_view)

    h.addWidget(right, 1)

    # ============================================================
    #  Логика
    # ============================================================

    def update_deck_list():
        deck_list.clear()
        for i, deck in enumerate(st["decks"]):
            stats = deck.stats()
            badge = ""
            if stats["due"] > 0:
                badge = f"  🔴 {stats['due']}"
            elif stats["new"] > 0:
                badge = f"  🆕 {stats['new']}"
            elif stats["total"] > 0:
                badge = "  ✓"

            item = QListWidgetItem(f"📚  {deck.name}  ({stats['total']}){badge}")
            item.setData(Qt.UserRole, i)
            deck_list.addItem(item)

    def update_stats_box():
        if st["current_deck"] is None:
            stats_box.setText("Выбери колоду для статистики")
            return
        s = st["current_deck"].stats()
        stats_box.setText(
            f"📊  Карточек: {s['total']}\n"
            f"🔴 К повтору: {s['due']}\n"
            f"🆕 Новых: {s['new']}\n"
            f"✓ Выучено: {s['learned']}\n"
            f"🎯 Точность: {s['accuracy']:.0f}%\n"
            f"📈 Всего ответов: {s['total_reviews']}"
        )

    def update_cards_list():
        cards_list.clear()
        if st["current_deck"] is None:
            return
        for i, card in enumerate(st["current_deck"].cards):
            # Индикатор состояния
            if card.total_reviews == 0:
                status = "🆕"
            elif card.is_due():
                status = "🔴"
            elif card.interval >= 21:
                status = "✓"
            else:
                status = "🟡"

            q = card.question
            if len(q) > 60:
                q = q[:58] + "…"
            q = q.replace("\n", " ")

            item = QListWidgetItem(f"{status}  {q}")
            item.setData(Qt.UserRole, i)
            # Тултип с полной инфой
            tip = (
                f"Вопрос: {card.question}\n\n"
                f"Ответ: {card.answer}\n\n"
                f"Повторений: {card.total_reviews}\n"
                f"Правильных: {card.correct_reviews}\n"
                f"Интервал: {card.interval} дн.\n"
                f"Лёгкость: {card.easiness:.2f}"
            )
            item.setToolTip(tip)
            cards_list.addItem(item)

    def select_deck(index: int):
        if not (0 <= index < len(st["decks"])):
            return
        st["current_deck"] = st["decks"][index]
        deck_title_lbl.setText(f"📚  {st['current_deck'].name}")
        train_btn.setEnabled(len(st["current_deck"].cards) > 0)
        add_card_btn.setEnabled(True)
        update_cards_list()
        update_stats_box()

    def on_deck_click(item):
        idx = item.data(Qt.UserRole)
        if idx is not None:
            select_deck(idx)

    deck_list.itemClicked.connect(on_deck_click)

    # ============================================================
    #  Создание/удаление колод
    # ============================================================

    def add_deck():
        name, ok = QInputDialog.getText(root, "Новая колода",
                                          "Название колоды:")
        if not ok or not name.strip():
            return
        deck = Deck(name.strip())
        st["decks"].append(deck)
        save_decks()
        update_deck_list()
        select_deck(len(st["decks"]) - 1)

    add_deck_btn.clicked.connect(add_deck)

    def deck_context(pos):
        item = deck_list.itemAt(pos)
        if item is None:
            return
        idx = item.data(Qt.UserRole)
        if idx is None:
            return
        menu = make_menu(deck_list)
        deck = st["decks"][idx]

        a_train = menu.addAction("🎯 Тренировать колоду")
        a_train.triggered.connect(lambda: start_training(idx))

        a_edit = menu.addAction("✏️ Переименовать")
        def do_rename():
            new_name, ok = QInputDialog.getText(
                root, "Переименовать", "Новое название:", text=deck.name)
            if ok and new_name.strip():
                deck.name = new_name.strip()
                save_decks()
                update_deck_list()
        a_edit.triggered.connect(do_rename)

        a_export = menu.addAction("💾 Экспорт в файл VFS")
        def do_export():
            export_deck(idx)
        a_export.triggered.connect(do_export)

        menu.addSeparator()

        a_del = menu.addAction("🗑 Удалить колоду")
        def do_del():
            ans = QMessageBox.question(
                root, "Удалить колоду",
                f"Удалить «{deck.name}»?\nВсе {len(deck.cards)} карточек будут удалены.",
                QMessageBox.Yes | QMessageBox.No)
            if ans == QMessageBox.Yes:
                st["decks"].pop(idx)
                save_decks()
                update_deck_list()
                if st["current_deck"] is deck:
                    st["current_deck"] = None
                    deck_title_lbl.setText("Выбери колоду")
                    train_btn.setEnabled(False)
                    add_card_btn.setEnabled(False)
                    cards_list.clear()
                    stats_box.setText("Выбери колоду для статистики")
        a_del.triggered.connect(do_del)

        menu.exec(deck_list.mapToGlobal(pos))

    deck_list.setContextMenuPolicy(Qt.CustomContextMenu)
    deck_list.customContextMenuRequested.connect(deck_context)

    def export_deck(idx: int):
        """Сохраняет колоду в /Documents/имя.json."""
        if vfs is None:
            return
        deck = st["decks"][idx]
        name = deck.name.replace(" ", "_").replace("/", "_")
        path = f"/Documents/{name}.json"
        try:
            vfs.mkdir("/Documents")
            vfs.write_text(path,
                json.dumps(deck.to_dict(), ensure_ascii=False, indent=2))
            if desktop and hasattr(desktop, "notifications"):
                desktop.notifications.push("Экспорт", f"Колода → {path}")
            QMessageBox.information(root, "Экспорт",
                f"Колода сохранена:\n{path}")
        except Exception as e:
            QMessageBox.warning(root, "Ошибка", str(e))

    # ============================================================
    #  Создание/редактирование карточек
    # ============================================================

    def add_card():
        if st["current_deck"] is None:
            return
        dlg = CardEditDialog(parent=root)
        if dlg.exec() != QDialog.Accepted:
            return
        data = dlg.get_data()
        if not data["question"] or not data["answer"]:
            QMessageBox.warning(root, "Ошибка",
                "Вопрос и ответ обязательны.")
            return
        card = Card(data["question"], data["answer"], data["hint"])
        st["current_deck"].cards.append(card)
        save_decks()
        update_cards_list()
        update_stats_box()
        update_deck_list()

    add_card_btn.clicked.connect(add_card)

    def edit_card(item):
        idx = item.data(Qt.UserRole)
        if idx is None or st["current_deck"] is None:
            return
        card = st["current_deck"].cards[idx]
        dlg = CardEditDialog(card, parent=root)
        if dlg.exec() != QDialog.Accepted:
            return
        data = dlg.get_data()
        if not data["question"] or not data["answer"]:
            return
        card.question = data["question"]
        card.answer = data["answer"]
        card.hint = data["hint"]
        save_decks()
        update_cards_list()

    cards_list.itemDoubleClicked.connect(edit_card)

    def card_context(pos):
        item = cards_list.itemAt(pos)
        if item is None:
            return
        idx = item.data(Qt.UserRole)
        if idx is None or st["current_deck"] is None:
            return
        menu = make_menu(cards_list)

        a_edit = menu.addAction("✏️ Редактировать")
        a_edit.triggered.connect(lambda: edit_card(item))

        a_reset = menu.addAction("🔄 Сбросить прогресс")
        def do_reset():
            card = st["current_deck"].cards[idx]
            card.interval = 0
            card.easiness = 2.5
            card.reps = 0
            card.lapses = 0
            card.due = time.time()
            card.total_reviews = 0
            card.correct_reviews = 0
            save_decks()
            update_cards_list()
            update_stats_box()
        a_reset.triggered.connect(do_reset)

        menu.addSeparator()

        a_del = menu.addAction("🗑 Удалить карточку")
        def do_del():
            st["current_deck"].cards.pop(idx)
            save_decks()
            update_cards_list()
            update_stats_box()
            update_deck_list()
        a_del.triggered.connect(do_del)

        menu.exec(cards_list.mapToGlobal(pos))

    cards_list.setContextMenuPolicy(Qt.CustomContextMenu)
    cards_list.customContextMenuRequested.connect(card_context)

    # ============================================================
    #  Тренировка
    # ============================================================

    def start_training(idx: int = None):
        if idx is None:
            if st["current_deck"] is None:
                return
            deck = st["current_deck"]
        else:
            deck = st["decks"][idx]

        # Переключаемся на страницу тренировки
        right.setCurrentIndex(1)
        training_view.start(deck)

    train_btn.clicked.connect(lambda: start_training())

    def on_training_finished(session):
        # Сохраняем прогресс
        save_decks()
        # Обновляем UI
        update_cards_list()
        update_stats_box()
        update_deck_list()

        # Уведомление
        if desktop and hasattr(desktop, "notifications"):
            answered = session["forgot"] + session["hard"] + session["easy"]
            desktop.notifications.push(
                "🎴 Тренировка завершена",
                f"Карточек: {answered}  ·  "
                f"❌ {session['forgot']}  🟠 {session['hard']}  🟢 {session['easy']}")

        # Возврат к списку карточек через небольшую задержку
        QTimer.singleShot(1500, lambda: right.setCurrentIndex(0))

    training_view.finished.connect(on_training_finished)

    # Кнопка возврата из тренировки (Esc)
    def key_back(e):
        if e.key() == Qt.Key_Escape and right.currentIndex() == 1:
            right.setCurrentIndex(0)
            update_cards_list()
            update_stats_box()
            update_deck_list()
            e.accept()
            return
        super(QWidget, root).keyPressEvent(e)

    root.keyPressEvent = key_back
    root.setFocusPolicy(Qt.StrongFocus)

    # ============================================================
    #  Старт
    # ============================================================

    update_deck_list()
    update_stats_box()

    # Если колод нет — создаём пример
    if not st["decks"]:
        example = Deck("Английские слова")
        example.cards = [
            Card("cat", "кошка"),
            Card("dog", "собака"),
            Card("house", "дом"),
            Card("car", "машина"),
            Card("book", "книга"),
        ]
        st["decks"].append(example)
        save_decks()
        update_deck_list()

    # Автовыбор первой колоды
    if st["decks"]:
        select_deck(0)
        deck_list.setCurrentRow(0)

    right.setCurrentIndex(0)

    return root