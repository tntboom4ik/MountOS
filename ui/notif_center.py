"""
MountOS — Центр уведомлений.
Выезжающая панель справа с историей уведомлений.
"""
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                                QPushButton, QScrollArea, QFrame,
                                QGraphicsDropShadowEffect)
from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QPoint, QTimer
from PySide6.QtGui import QColor, QIcon

from ui.icons import get_icon
from ui.settings_state import state
from system.notify_history import history, pretty_time


PANEL_WIDTH  = 380
PANEL_MARGIN = 12


class NotifCard(QWidget):
    """Карточка одного уведомления."""

    def __init__(self, entry: dict, index: int, on_remove, on_mark_read, parent=None):
        super().__init__(parent)
        self.entry = entry
        self.index = index
        self._on_remove = on_remove
        self._on_mark_read = on_mark_read

        self.setStyleSheet(self._card_style(entry.get("read", False)))

        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 10, 10, 10)
        lay.setSpacing(12)

        # Иконка
        icon_lbl = QLabel()
        icon_name = entry.get("icon") or "settings"
        icon_lbl.setPixmap(get_icon(icon_name, 24, state().get("accent")))
        icon_lbl.setFixedSize(28, 28)
        lay.addWidget(icon_lbl, 0, Qt.AlignTop)

        # Текст
        col = QVBoxLayout()
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(2)

        title = QLabel(entry.get("title", "Без названия"))
        title.setStyleSheet("""
            color: white;
            font-size: 13px;
            font-weight: 600;
            background: transparent;
        """)
        title.setWordWrap(True)
        col.addWidget(title)

        if entry.get("text"):
            text = QLabel(entry["text"])
            text.setStyleSheet("""
                color: rgba(255,255,255,0.65);
                font-size: 12px;
                background: transparent;
            """)
            text.setWordWrap(True)
            col.addWidget(text)

        time_lbl = QLabel(pretty_time(entry.get("time", 0)))
        time_lbl.setStyleSheet("""
            color: rgba(255,255,255,0.40);
            font-size: 10px;
            background: transparent;
        """)
        col.addWidget(time_lbl)

        lay.addLayout(col, 1)

        # Кнопка удаления
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(22, 22)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setToolTip("Удалить уведомление")
        close_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: rgba(255,255,255,0.45);
                border: none;
                border-radius: 11px;
                font-size: 12px;
            }
            QPushButton:hover {
                background: rgba(255,107,138,0.35);
                color: white;
            }
        """)
        close_btn.clicked.connect(lambda: self._on_remove(self.index))
        lay.addWidget(close_btn, 0, Qt.AlignTop)

        # Клик по карточке — отметить прочитанным
        self.setCursor(Qt.PointingHandCursor)

    def _card_style(self, read: bool):
        if read:
            bg = "rgba(255,255,255,0.04)"
            border = "rgba(255,255,255,0.08)"
        else:
            bg = "rgba(110,198,255,0.10)"
            border = "rgba(110,198,255,0.35)"
        return f"""
            NotifCard {{
                background: {bg};
                border: 1px solid {border};
                border-radius: 12px;
            }}
            NotifCard:hover {{
                background: rgba(255,255,255,0.10);
                border: 1px solid rgba(255,255,255,0.18);
            }}
        """

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._on_mark_read(self.index)
        super().mousePressEvent(e)


class NotificationCenterPanel(QWidget):
    """Выезжающая панель справа."""

    def __init__(self, host: QWidget):
        super().__init__(host)
        self.host = host
        self.setFixedWidth(PANEL_WIDTH)
        self.setAttribute(Qt.WA_TranslucentBackground)

        # Начальная позиция — за правым краем
        self._visible = False
        self.hide()

        # Внешний layout с отступом под тень
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, PANEL_MARGIN, PANEL_MARGIN, PANEL_MARGIN)
        outer.setSpacing(0)

        # Стеклянная карточка
        card = QWidget(self)
        card.setObjectName("card")
        card.setStyleSheet("""
            QWidget#card {
                background: rgba(22, 28, 44, 0.96);
                border: 1px solid rgba(255,255,255,0.12);
                border-radius: 20px;
            }
        """)
        outer.addWidget(card)

        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(60)
        shadow.setOffset(-8, 8)
        shadow.setColor(QColor(0, 0, 0, 180))
        card.setGraphicsEffect(shadow)

        cl = QVBoxLayout(card)
        cl.setContentsMargins(16, 16, 16, 16)
        cl.setSpacing(12)

        # Заголовок
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)

        title = QLabel("Уведомления")
        title.setStyleSheet("""
            color: white;
            font-size: 16px;
            font-weight: 600;
            letter-spacing: 0.5px;
            background: transparent;
        """)
        header.addWidget(title)

        self.counter = QLabel("")
        self.counter.setStyleSheet("""
            color: #6EC6FF;
            font-size: 12px;
            font-weight: 600;
            background: rgba(110,198,255,0.15);
            border: 1px solid rgba(110,198,255,0.45);
            border-radius: 9px;
            padding: 2px 8px;
        """)
        header.addWidget(self.counter)

        header.addStretch(1)

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(28, 28)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255,255,255,0.06);
                color: rgba(255,255,255,0.75);
                border: 1px solid rgba(255,255,255,0.10);
                border-radius: 8px;
                font-size: 13px;
            }
            QPushButton:hover {
                background: rgba(255,107,138,0.35);
                color: white;
            }
        """)
        close_btn.clicked.connect(self.hide_panel)
        header.addWidget(close_btn)

        cl.addLayout(header)

        # Кнопки управления
        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(8)

        read_all_btn = QPushButton("Прочитать все")
        read_all_btn.setCursor(Qt.PointingHandCursor)
        read_all_btn.setStyleSheet(self._small_btn_style())
        read_all_btn.clicked.connect(self._mark_all_read)
        actions.addWidget(read_all_btn)

        clear_btn = QPushButton("Очистить")
        clear_btn.setCursor(Qt.PointingHandCursor)
        clear_btn.setStyleSheet(self._small_btn_style(danger=True))
        clear_btn.clicked.connect(self._clear_all)
        actions.addWidget(clear_btn)

        actions.addStretch(1)
        cl.addLayout(actions)

        # Список
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
            QScrollBar:vertical {
                background: transparent; width: 6px; margin: 2px;
            }
            QScrollBar::handle:vertical {
                background: rgba(255,255,255,0.20);
                border-radius: 3px; min-height: 24px;
            }
            QScrollBar::handle:vertical:hover {
                background: rgba(255,255,255,0.35);
            }
            QScrollBar::add-line, QScrollBar::sub-line { height: 0; }
        """)
        cl.addWidget(self.scroll, 1)

        self._list_holder = QWidget()
        self._list_holder.setStyleSheet("background: transparent;")
        self._list_lay = QVBoxLayout(self._list_holder)
        self._list_lay.setContentsMargins(0, 0, 0, 0)
        self._list_lay.setSpacing(8)
        self._list_lay.addStretch(1)
        self.scroll.setWidget(self._list_holder)

        # Пустое состояние
        self.empty_lbl = QLabel("Уведомлений пока нет")
        self.empty_lbl.setAlignment(Qt.AlignCenter)
        self.empty_lbl.setStyleSheet("""
            color: rgba(255,255,255,0.40);
            font-size: 13px;
            padding: 40px 12px;
            background: transparent;
        """)
        self._list_lay.insertWidget(0, self.empty_lbl)

        # Позиционируем в хосте
        self._reposition()

        # Авто-обновление при новых уведомлениях
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh_if_visible)
        self._timer.start(2000)

    # ---------- Стили ----------

    def _small_btn_style(self, danger: bool = False):
        if danger:
            return """
                QPushButton {
                    background: rgba(255,107,138,0.15);
                    color: #FFA0B4;
                    border: 1px solid rgba(255,107,138,0.40);
                    border-radius: 9px;
                    padding: 6px 12px;
                    font-size: 11px;
                }
                QPushButton:hover {
                    background: rgba(255,107,138,0.35);
                    color: white;
                }
            """
        return """
            QPushButton {
                background: rgba(255,255,255,0.06);
                color: rgba(255,255,255,0.85);
                border: 1px solid rgba(255,255,255,0.10);
                border-radius: 9px;
                padding: 6px 12px;
                font-size: 11px;
            }
            QPushButton:hover {
                background: rgba(255,255,255,0.18);
                color: white;
            }
        """

    # ---------- Позиционирование ----------

    def _reposition(self):
        h = self.host.height()
        self.setFixedHeight(h - 2 * PANEL_MARGIN)
        # Скрытая позиция — за правым краем
        self._hidden_x = self.host.width() + 10
        # Видимая позиция
        self._shown_x = self.host.width() - PANEL_WIDTH
        self._y = PANEL_MARGIN

        if self._visible:
            self.move(self._shown_x, self._y)
        else:
            self.move(self._hidden_x, self._y)

    def resizeEvent(self, e):
        self._reposition()
        super().resizeEvent(e)

    # ---------- Показ / скрытие ----------

    def show_panel(self):
        if self._visible:
            return
        self._reposition()
        self._refresh()
        self.show()
        self.raise_()

        anim = QPropertyAnimation(self, b"pos")
        anim.setDuration(240)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.setStartValue(QPoint(self._hidden_x, self._y))
        anim.setEndValue(QPoint(self._shown_x, self._y))
        anim.start()
        self._anim = anim
        self._visible = True

    def hide_panel(self):
        if not self._visible:
            return
        anim = QPropertyAnimation(self, b"pos")
        anim.setDuration(200)
        anim.setEasingCurve(QEasingCurve.InCubic)
        anim.setStartValue(QPoint(self._shown_x, self._y))
        anim.setEndValue(QPoint(self._hidden_x, self._y))
        anim.finished.connect(self._after_hide)
        anim.start()
        self._anim = anim
        self._visible = False

    def _after_hide(self):
        if not self._visible:
            self.hide()

    def toggle(self):
        if self._visible:
            self.hide_panel()
        else:
            self.show_panel()

    # ---------- Обновление ----------

    def _refresh_if_visible(self):
        if self._visible:
            self._refresh()

    def _refresh(self):
        # Очистить старые карточки (всё, кроме stretch и empty_lbl)
        for i in reversed(range(self._list_lay.count())):
            it = self._list_lay.itemAt(i)
            w = it.widget()
            if w is self.empty_lbl:
                continue
            if w is not None:
                w.setParent(None)

        items = history().latest(50)

        if not items:
            self.empty_lbl.show()
        else:
            self.empty_lbl.hide()
            # Собираем карточки в обратном порядке (свежие сверху)
            for idx in range(len(items) - 1, -1, -1):
                entry = items[idx]
                # индекс в полной истории
                full_list = history().all()
                try:
                    real_index = len(full_list) - len(items) + idx
                except Exception:
                    real_index = idx
                card = NotifCard(entry, real_index,
                                 on_remove=self._remove_index,
                                 on_mark_read=self._mark_read_index)
                self._list_lay.insertWidget(0, card)

        # Счётчик непрочитанных
        n = history().unread_count()
        if n > 0:
            self.counter.setText(f"{n}")
            self.counter.show()
        else:
            self.counter.hide()

    # ---------- Действия ----------

    def _mark_read_index(self, index: int):
        history().mark_read(index)
        self._refresh()

    def _remove_index(self, index: int):
        history().remove(index)
        self._refresh()

    def _mark_all_read(self):
        history().mark_all_read()
        self._refresh()

    def _clear_all(self):
        history().clear()
        self._refresh()