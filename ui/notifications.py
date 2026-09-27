"""
MountOS — Всплывающие уведомления.

Каждое уведомление:
  • показывается в правом верхнем углу
  • записывается в историю (system.notify_history)
  • обновляет счётчик непрочитанных на панели
  • попадает в центр уведомлений (если открыт)
"""
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                                QPushButton, QGraphicsDropShadowEffect,
                                QApplication)
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QPoint
from PySide6.QtGui import QColor, QIcon

from ui.icons import get_icon
from ui.settings_state import state
from system.notify_history import history


# ============================================================
#  Одно уведомление
# ============================================================

class Notification(QWidget):
    def __init__(self, parent, title: str, text: str,
                 duration_ms: int = 3200,
                 app_id: str = "", icon_name: str = "bell"):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(340, 96)
        self.setWindowFlags(Qt.Widget)

        self._duration_ms = duration_ms
        self._app_id = app_id
        self._icon_name = icon_name

        # Внешний layout
        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 10)

        # Внутренняя карточка
        card = QWidget(self)
        card.setObjectName("notifCard")
        card.setStyleSheet("""
            QWidget#notifCard {
                background: rgba(28, 34, 54, 0.98);
                border: 1px solid rgba(110, 198, 255, 0.40);
                border-radius: 16px;
            }
        """)
        outer.addWidget(card)

        # Тень
        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(40)
        shadow.setOffset(0, 8)
        shadow.setColor(QColor(0, 0, 0, 180))
        card.setGraphicsEffect(shadow)

        # Содержимое
        cl = QHBoxLayout(card)
        cl.setContentsMargins(14, 12, 12, 12)
        cl.setSpacing(12)

        # Иконка
        self.icon_lbl = QLabel()
        self.icon_lbl.setFixedSize(28, 28)
        self.icon_lbl.setStyleSheet("background: transparent; border: none;")
        self._refresh_icon()
        cl.addWidget(self.icon_lbl, 0, Qt.AlignTop)

        # Текст
        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(2)

        self.title_lbl = QLabel(title)
        self.title_lbl.setStyleSheet("""
            color: white;
            font-size: 13px;
            font-weight: 600;
            background: transparent;
            border: none;
        """)
        self.title_lbl.setWordWrap(True)
        text_col.addWidget(self.title_lbl)

        if text:
            self.text_lbl = QLabel(text)
            self.text_lbl.setStyleSheet("""
                color: rgba(255,255,255,0.72);
                font-size: 12px;
                background: transparent;
                border: none;
            """)
            self.text_lbl.setWordWrap(True)
            text_col.addWidget(self.text_lbl)

        cl.addLayout(text_col, 1)

        # Кнопка закрытия
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(22, 22)
        close_btn.setCursor(Qt.PointingHandCursor)
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
        close_btn.clicked.connect(self._dismiss)
        cl.addWidget(close_btn, 0, Qt.AlignTop)

        # Автозакрытие
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._dismiss)
        self._timer.start(duration_ms)

    def _refresh_icon(self):
        try:
            accent = state().get("accent", "#6EC6FF")
            pm = get_icon(self._icon_name, 24, accent)
            self.icon_lbl.setPixmap(pm)
        except Exception:
            pass

    def _dismiss(self):
        anim = QPropertyAnimation(self, b"windowOpacity")
        anim.setDuration(220)
        anim.setEasingCurve(QEasingCurve.InCubic)
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        anim.finished.connect(self.deleteLater)
        anim.start()
        self._anim = anim


# ============================================================
#  Менеджер уведомлений
# ============================================================

class NotificationCenter:
    """Стек уведомлений в правом верхнем углу."""

    MARGIN_TOP = 60      # ниже верхней панели
    MARGIN_RIGHT = 16
    SPACING = 10

    def __init__(self, host: QWidget):
        self.host = host
        self.items = []    # список живых QWidget-ов

    # ---------- Показ ----------

    def push(self, title: str, text: str = "",
             duration_ms: int = 3200,
             app_id: str = "", icon_name: str = "bell"):
        """
        Показать уведомление.

        Дополнительно:
          • пишет в историю system.notify_history
          • обновляет бейдж в панели
          • если открыт центр уведомлений — обновляет его
        """
        # 1. Запись в историю
        try:
            history().add(title, text, app_id=app_id, icon=icon_name)
        except Exception as e:
            print(f"[Notifications] история упала: {e}")

        # 2. Всплывающее окно
        n = Notification(self.host, title, text,
                         duration_ms=duration_ms,
                         app_id=app_id, icon_name=icon_name)
        n.show()
        n.raise_()

        self.items.append(n)

        # 3. Плавное появление
        n.setWindowOpacity(0.0)
        anim = QPropertyAnimation(n, b"windowOpacity")
        anim.setDuration(200)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.start()
        n._show_anim = anim

        # 4. Репозиционирование стопкой
        self._reposition()

        # 5. Подчистить, когда уведомление закроется
        n.destroyed.connect(self._on_destroyed)

        # 6. Обновить UI (панель + центр)
        self._refresh_ui()

    # ---------- Позиционирование ----------

    def _reposition(self):
        """Расставляет уведомления стопкой сверху вниз."""
        y = self.MARGIN_TOP
        for n in self.items:
            try:
                if not n.isVisible():
                    continue
                x = self.host.width() - n.width() - self.MARGIN_RIGHT
                n.move(max(0, x), y)
                y += n.height() + self.SPACING
            except RuntimeError:
                continue

    def _on_destroyed(self, *_):
        # Убираем мёртвые из списка
        self.items = [it for it in self.items
                      if _is_alive(it)]
        self._reposition()

    # ---------- Синхронизация UI ----------

    def _refresh_ui(self):
        """Обновляет панель и центр уведомлений, если они есть."""
        # Панель
        try:
            p = self.host.findChild(QWidget, "TopPanel")
            if p and hasattr(p, "_refresh_notif_icon"):
                p._refresh_notif_icon()
        except Exception:
            pass

        # Центр уведомлений — если открыт
        try:
            nc = getattr(self.host, "notif_center", None)
            if nc and getattr(nc, "_visible", False):
                nc._refresh()
        except Exception:
            pass


# ============================================================
#  Утилита: жив ли Qt-объект
# ============================================================

def _is_alive(obj) -> bool:
    """True, если C++-объект ещё существует."""
    try:
        # Если объект удалён, любое обращение бросит RuntimeError
        obj.objectName()
        return True
    except RuntimeError:
        return False