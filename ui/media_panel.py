"""
MountOS — Мини-плеер в верхней панели.

Показывает играющий трек и кнопки управления:
  • Название трека и исполнителя (бегущая строка если длинное)
  • Прогресс-бар с текущей позицией
  • Кнопки: play/pause, prev, next
  • Клик по названию → открыть приложение Музыка
  • Скрыт, когда ничего не играет

Работает через центральный PlayerState — единый для всех плееров
(Музыка, Радио, любые приложения, использующие QMediaPlayer).

API:
    from ui.media_panel import MediaPanel, player_state
    panel = MediaPanel(host)
    
    # Любое приложение может сообщить о треке:
    player_state().set_track("Название", "Автор", duration_ms)
    player_state().set_position(position_ms)
    player_state().set_state(playing=True)
"""

from PySide6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QLabel,
                                QPushButton, QSlider, QSizePolicy)
from PySide6.QtCore import Qt, QTimer, QObject, Signal
from PySide6.QtGui import QIcon, QColor

from ui.icons import get_icon
from ui.settings_state import state


# ============================================================
#  Глобальное состояние плеера
# ============================================================

class PlayerState(QObject):
    """
    Синглтон — общее состояние медиаплеера.
    Любое приложение может обновлять его через set_* методы,
    а панель автоматически отобразит.
    """

    changed = Signal()   # что-то изменилось

    def __init__(self):
        super().__init__()
        self.title = ""
        self.artist = ""
        self.duration_ms = 0
        self.position_ms = 0
        self.is_playing = False
        self.is_active = False       # есть ли вообще трек
        self.source_app = ""          # какое приложение
        self.controls_enabled = True  # есть ли внешние кнопки (play/pause и т.д.)

    # ---- API для приложений ----

    def set_track(self, title: str, artist: str = "",
                  duration_ms: int = 0, source: str = ""):
        self.title = title or ""
        self.artist = artist or ""
        self.duration_ms = max(0, duration_ms)
        self.source_app = source
        self.is_active = bool(title)
        self.changed.emit()

    def set_position(self, position_ms: int):
        self.position_ms = max(0, position_ms)
        self.changed.emit()

    def set_state(self, playing: bool):
        self.is_playing = bool(playing)
        self.changed.emit()

    def stop(self):
        """Очистить состояние (ничего не играет)."""
        self.title = ""
        self.artist = ""
        self.duration_ms = 0
        self.position_ms = 0
        self.is_playing = False
        self.is_active = False
        self.source_app = ""
        self.changed.emit()


_player_state_instance = None


def player_state() -> PlayerState:
    global _player_state_instance
    if _player_state_instance is None:
        _player_state_instance = PlayerState()
    return _player_state_instance


# ============================================================
#  Виджет панели
# ============================================================

class MediaPanel(QWidget):
    """
    Мини-плеер для верхней панели MountOS.
    Автоматически показывается, когда есть активный трек.
    """

    def __init__(self, host=None, parent=None):
        super().__init__(parent)
        self.host = host
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        self.setFixedHeight(36)

        self._scroll_offset = 0
        self._scroll_timer = QTimer(self)
        self._scroll_timer.setInterval(250)
        self._scroll_timer.timeout.connect(self._scroll_tick)

        # ---- Layout ----
        h = QHBoxLayout(self)
        h.setContentsMargins(8, 0, 8, 0)
        h.setSpacing(8)

        # ---- Иконка ----
        self.icon_lbl = QLabel()
        self.icon_lbl.setFixedSize(20, 20)
        self.icon_lbl.setPixmap(get_icon("music", 18, "#6EC6FF"))
        self.icon_lbl.setStyleSheet("background: transparent; border: none;")
        self.icon_lbl.setCursor(Qt.PointingHandCursor)
        self.icon_lbl.mousePressEvent = lambda e: self._open_player_app()
        h.addWidget(self.icon_lbl)

        # ---- Название трека ----
        self.title_lbl = QLabel("")
        self.title_lbl.setFixedWidth(180)
        self.title_lbl.setStyleSheet("""
            color: white;
            font-size: 11px;
            font-weight: 500;
            background: transparent;
            border: none;
        """)
        self.title_lbl.setCursor(Qt.PointingHandCursor)
        self.title_lbl.mousePressEvent = lambda e: self._open_player_app()
        h.addWidget(self.title_lbl)

        # ---- Прогресс-бар ----
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, 1000)
        self.slider.setValue(0)
        self.slider.setFixedWidth(100)
        self.slider.setStyleSheet("""
            QSlider::groove:horizontal {
                height: 3px;
                background: rgba(255,255,255,0.15);
                border-radius: 2px;
            }
            QSlider::sub-page:horizontal {
                background: #6EC6FF;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: white;
                width: 10px;
                margin: -4px 0;
                border-radius: 5px;
            }
            QSlider::handle:horizontal:hover { background: #A0DEFF; }
        """)
        self.slider.sliderMoved.connect(self._on_seek)
        h.addWidget(self.slider)

        # ---- Кнопки управления ----
        self.prev_btn = self._make_ctrl_btn("back", "Предыдущий трек",
                                             self._on_prev)
        h.addWidget(self.prev_btn)

        self.play_btn = self._make_ctrl_btn("grid", "Играть / пауза",
                                             self._on_play)
        h.addWidget(self.play_btn)

        self.next_btn = self._make_ctrl_btn("forward", "Следующий трек",
                                             self._on_next)
        h.addWidget(self.next_btn)

        # ---- Подписка на состояние ----
        player_state().changed.connect(self._on_state_changed)

        # Изначально скрыт
        self.hide()

        # ---- Автообновление ----
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(500)
        self._refresh_timer.timeout.connect(self._update)
        self._refresh_timer.start()

    # ------------------------------------------------------------
    #  Вспомогательные
    # ------------------------------------------------------------

    def _make_ctrl_btn(self, icon_name: str, tooltip: str, callback) -> QPushButton:
        b = QPushButton()
        b.setFixedSize(28, 28)
        b.setCursor(Qt.PointingHandCursor)
        b.setToolTip(tooltip)
        b.setIcon(QIcon(get_icon(icon_name, 16, "#FFFFFF")))
        b.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                border-radius: 8px;
            }
            QPushButton:hover {
                background: rgba(255,255,255,0.15);
            }
            QPushButton:pressed {
                background: rgba(110,198,255,0.35);
            }
        """)
        b.clicked.connect(callback)
        return b

    # ------------------------------------------------------------
    #  Обновление UI
    # ------------------------------------------------------------

    def _on_state_changed(self):
        self._update()

    def _update(self):
        ps = player_state()

        # Показывать или скрывать
        if not ps.is_active:
            if self.isVisible():
                self.hide()
            return
        else:
            if not self.isVisible():
                self.show()

        # Название
        title = ps.title or "—"
        if ps.artist:
            title = f"{ps.artist} — {title}"
        if len(title) > 30:
            title = title[:29] + "…"
        self.title_lbl.setText(title)

        # Иконка play/pause
        icon_name = "grid" if not ps.is_playing else "notes"
        # Лучше использовать существующие иконки
        if ps.is_playing:
            self.play_btn.setIcon(QIcon(get_icon("notes", 16, "#6EC6FF")))
        else:
            self.play_btn.setIcon(QIcon(get_icon("grid", 16, "#FFFFFF")))

        # Прогресс
        if ps.duration_ms > 0:
            value = int(ps.position_ms / ps.duration_ms * 1000)
            self.slider.blockSignals(True)
            self.slider.setValue(value)
            self.slider.blockSignals(False)

    def _scroll_tick(self):
        """Бегущая строка для длинных названий."""
        ps = player_state()
        title = ps.title or ""
        if ps.artist:
            title = f"{ps.artist} — {title}"
        if len(title) <= 30:
            self._scroll_timer.stop()
            return
        # Прокрутка по символам
        self._scroll_offset = (self._scroll_offset + 1) % (len(title) + 5)
        display = title + "   "
        start = self._scroll_offset
        text = (display * 2)[start:start + 30]
        self.title_lbl.setText(text)

    # ------------------------------------------------------------
    #  Управление
    # ------------------------------------------------------------

    def _open_player_app(self):
        """Открыть главное приложение-источник."""
        ps = player_state()
        app_id = ps.source_app or "music"
        if self.host and hasattr(self.host, "open_app"):
            self.host.open_app(app_id)
            return
        from PySide6.QtWidgets import QApplication
        for top in QApplication.topLevelWidgets():
            if hasattr(top, "open_app"):
                top.open_app(app_id)
                return

    def _on_play(self):
        """Отправить сигнал play/pause активному приложению."""
        # Приложение само решит, что делать — через сигнал
        ps = player_state()
        ps.set_state(not ps.is_playing)
        # Уведомляем приложения через специальный сигнал
        self._emit_command("toggle")

    def _on_prev(self):
        self._emit_command("prev")

    def _on_next(self):
        self._emit_command("next")

    def _on_seek(self, value):
        """Перемотка."""
        ps = player_state()
        if ps.duration_ms > 0:
            ms = int(value / 1000 * ps.duration_ms)
            ps.set_position(ms)
            self._emit_command("seek", ms)

    # ------------------------------------------------------------
    #  Команды для приложений
    # ------------------------------------------------------------

    def _emit_command(self, cmd: str, value=None):
        """
        Отправляет команду активному медиаприложению.
        Через QApplication — находим окна с методом media_command().
        """
        from PySide6.QtWidgets import QApplication
        for top in QApplication.topLevelWidgets():
            if hasattr(top, "media_command"):
                try:
                    top.media_command(cmd, value)
                except Exception as e:
                    print(f"[MediaPanel] command error: {e}")