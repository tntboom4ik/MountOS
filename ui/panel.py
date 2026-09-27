"""
MountOS — Верхняя панель.
Логотип, меню приложений, часы, центр уведомлений.
Поддерживает локализацию (ru/en) и авто-обновление при смене языка.
"""
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton, QSizePolicy
from PySide6.QtCore import Qt, QSize, QTimer
from PySide6.QtGui import QIcon

from ui.settings_state import state
from ui.icons import get_icon
from system.i18n import tr, on_change
from system.notify_history import history


class TopPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(44)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 0, 16, 0)
        lay.setSpacing(8)

        # ---------- Логотип + меню приложений ----------
        self.menu_btn = QPushButton("◆")
        self.menu_btn.setFixedSize(32, 32)
        self.menu_btn.setCursor(Qt.PointingHandCursor)
        self.menu_btn.setToolTip(tr("appmenu.title"))
        self.menu_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                border-radius: 10px;
                font-size: 16px;
            }
            QPushButton:hover {
                background: rgba(255,255,255,0.10);
            }
            QPushButton:pressed {
                background: rgba(110,198,255,0.30);
            }
        """)
        self.menu_btn.clicked.connect(self._on_menu_click)
        lay.addWidget(self.menu_btn)

        self.logo = QLabel("MountOS")
        self.logo.setStyleSheet("""
            color: rgba(255,255,255,0.95);
            font-size: 14px;
            font-weight: 600;
            letter-spacing: 1.2px;
        """)
        lay.addWidget(self.logo)

        lay.addStretch(1)

        # ---------- Часы ----------
        self.clock = QLabel("--:--")
        self.clock.setStyleSheet("""
            color: rgba(255,255,255,0.85);
            font-size: 14px;
            font-weight: 500;
            letter-spacing: 0.5px;
        """)
        lay.addWidget(self.clock)

        lay.addSpacing(10)

        # ---------- Кнопка центра уведомлений ----------
        self.notif_btn = QPushButton()
        self.notif_btn.setFixedSize(32, 32)
        self.notif_btn.setCursor(Qt.PointingHandCursor)
        self.notif_btn.setToolTip(tr("notif.center_title"))
        self.notif_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                border-radius: 10px;
            }
            QPushButton:hover {
                background: rgba(255,255,255,0.10);
            }
            QPushButton:pressed {
                background: rgba(110,198,255,0.30);
            }
        """)
        self.notif_btn.clicked.connect(self._on_notif_click)
        lay.addWidget(self.notif_btn)

        # ---------- Стиль панели ----------
        self.setStyleSheet("""
            TopPanel {
                background: rgba(255, 255, 255, 0.06);
                border-bottom: 1px solid rgba(255, 255, 255, 0.10);
            }
        """)

        # ---------- Подписки ----------
        state().changed.connect(self._on_state)
        on_change(self._on_language)

        # Таймер обновления бейджа уведомлений
        self._badge_timer = QTimer(self)
        self._badge_timer.timeout.connect(self._refresh_notif_icon)
        self._badge_timer.start(2000)

        # Первичная отрисовка
        self._apply_visibility()
        self._refresh_notif_icon()

    # ------------------------------------------------------------
    #  Обработчики
    # ------------------------------------------------------------

    def _on_state(self, key, val):
        if key == "show_clock":
            self._apply_visibility()
        elif key == "accent":
            self._refresh_notif_icon()

    def _on_language(self, lang):
        """Перерисовать тексты при смене языка."""
        self.menu_btn.setToolTip(tr("appmenu.title"))
        self.notif_btn.setToolTip(tr("notif.center_title"))

    def _apply_visibility(self):
        self.clock.setVisible(state().get("show_clock", True))

    def _on_menu_click(self):
        """Открыть меню приложений (AppMenu)."""
        d = self._desktop()
        if d and hasattr(d, "app_menu"):
            d.app_menu.toggle()

    def _on_notif_click(self):
        """Открыть центр уведомлений."""
        d = self._desktop()
        if d and hasattr(d, "notif_center"):
            d.notif_center.toggle()

    # ------------------------------------------------------------
    #  Утилиты
    # ------------------------------------------------------------

    def _desktop(self):
        """Находит Desktop через parent()."""
        p = self.parent()
        while p is not None:
            if hasattr(p, "notifications") and hasattr(p, "open_app"):
                return p
            p = p.parent()
        return None

    def _refresh_notif_icon(self):
        """Перерисовать иконку колокольчика + бейдж."""
        try:
            unread = history().unread_count()
        except Exception:
            unread = 0

        accent = state().get("accent", "#6EC6FF")
        # Цвет иконки: белый если нет непрочитанных, акцентный если есть
        icon_color = accent if unread > 0 else "#FFFFFF"
        icon = get_icon("bell", 22, icon_color)
        self.notif_btn.setIcon(QIcon(icon))
        self.notif_btn.setIconSize(QSize(20, 20))

        # Бейдж: показать как текст поверх (просто число в tooltip + цвет кнопки)
        if unread > 0:
            self.notif_btn.setToolTip(f"{tr('notif.center_title')} ({unread})")
        else:
            self.notif_btn.setToolTip(tr("notif.center_title"))

    # ------------------------------------------------------------
    #  Часы
    # ------------------------------------------------------------

    def set_time(self, text: str):
        self.clock.setText(text)