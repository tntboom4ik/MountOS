"""
MountOS — Ночной режим.

Автоматически включает тёплый фильтр после заданного часа
и выключает утром. Помогает глазам и не мешает сну.

Возможности:
  • Автовключение по расписанию (например, с 21:00 до 07:00)
  • Ручное включение/выключение
  • Плавное появление (не резко)
  • Регулировка интенсивности
  • Реакция на смену системного времени
  • Работает глобально — поверх всех окон MountOS

Использование:
    from system.night_mode import night
    night.enable()            # включить
    night.disable()           # выключить
    night.toggle()            # переключить
    night.is_active()         # True/False
    night.set_schedule(21, 7) # с 21:00 до 07:00
"""

from PySide6.QtCore import QObject, Signal, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QWidget, QApplication
from datetime import datetime


# ============================================================
#  Наложение (оверлей) для тёплого фильтра
# ============================================================

class NightOverlay(QWidget):
    """
    Полупрозрачный виджет поверх всего экрана.
    Не перехватывает клики (WindowTransparentForInput).
    """

    def __init__(self):
        super().__init__(None)
        self.setWindowFlags(
            self.windowFlags()
            | self.windowFlags().FramelessWindowHint
            | self.windowFlags().WindowStaysOnTopHint
            | self.windowFlags().Tool
            | self.windowFlags().WindowTransparentForInput
        )
        self.setAttribute(self.windowFlags().WA_TranslucentBackground)
        self.setAttribute(self.windowFlags().WA_TransparentForMouseEvents)
        self.setAttribute(self.windowFlags().WA_NoSystemBackground)

        # Цвет фильтра: тёплый оранжевый
        self._filter_color = QColor(255, 180, 90)
        self._alpha = 0           # текущая прозрачность 0..255
        self._target_alpha = 0    # куда идём
        self._max_alpha = 45      # максимальная интенсивность (не слишком сильно)

        # Таймер плавного появления/исчезновения
        self._fade_timer = QTimer(self)
        self._fade_timer.setInterval(16)   # ~60 FPS
        self._fade_timer.timeout.connect(self._fade_step)

        self.hide()

    # ------------------------------------------------------------
    #  Плавное появление / исчезновение
    # ------------------------------------------------------------

    def fade_to(self, target_alpha: int):
        self._target_alpha = max(0, min(255, target_alpha))
        if not self._fade_timer.isActive():
            self._fade_timer.start()
        if not self.isVisible() and self._target_alpha > 0:
            self.show()
            self.raise_()

    def _fade_step(self):
        if self._alpha < self._target_alpha:
            self._alpha = min(self._alpha + 3, self._target_alpha)
            self.update()
        elif self._alpha > self._target_alpha:
            self._alpha = max(self._alpha - 3, self._target_alpha)
            self.update()
        else:
            self._fade_timer.stop()
            if self._alpha == 0 and self.isVisible():
                self.hide()

    def paintEvent(self, e):
        if self._alpha <= 0:
            return
        from PySide6.QtGui import QPainter
        p = QPainter(self)
        c = QColor(self._filter_color)
        c.setAlpha(self._alpha)
        p.fillRect(self.rect(), c)
        p.end()

    def set_max_alpha(self, value: int):
        """Устанавливает максимальную интенсивность (0..100)."""
        self._max_alpha = max(0, min(100, value))

    def max_alpha(self) -> int:
        return self._max_alpha


# ============================================================
#  Менеджер ночного режима
# ============================================================

class NightMode(QObject):
    """
    Синглтон-менеджер ночного режима.
    Эмитит changed(active) при переключении.
    """

    changed = Signal(bool)   # True = включён

    def __init__(self):
        super().__init__()
        self._active = False
        self._auto_enabled = True     # по умолчанию авто включено
        self._start_hour = 21
        self._end_hour = 7
        self._intensity = 45          # 0..100
        self._connected = False

        # Оверлей
        self._overlay = None

        # Таймер проверки расписания (каждую минуту)
        self._schedule_timer = QTimer(self)
        self._schedule_timer.timeout.connect(self._check_schedule)

        # Подключаемся к настройкам
        self._connect_to_settings()

    def _connect_to_settings(self):
        if self._connected:
            return
        try:
            from ui.settings_state import state
            st = state()
            self._auto_enabled = st.get("night_auto", True)
            self._start_hour = st.get("night_start", 21)
            self._end_hour = st.get("night_end", 7)
            self._intensity = st.get("night_intensity", 45)
            st.changed.connect(self._on_settings_changed)
            self._connected = True

            # Запускаем проверку расписания
            self._schedule_timer.start(60 * 1000)   # раз в минуту
            self._check_schedule()
        except Exception as e:
            print(f"[NightMode] settings: {e}")

    def _on_settings_changed(self, key, value):
        if key == "night_auto":
            self._auto_enabled = bool(value)
            self._check_schedule()
        elif key == "night_start":
            self._start_hour = int(value)
        elif key == "night_end":
            self._end_hour = int(value)
        elif key == "night_intensity":
            self._intensity = max(0, min(100, int(value)))
            if self._overlay:
                self._overlay.set_max_alpha(self._intensity)
                if self._active:
                    self._overlay.fade_to(self._intensity * 255 // 100)
        elif key == "night_manual":
            # Ручное включение/выключение
            if value:
                self.enable()
            else:
                self.disable()

    # ------------------------------------------------------------
    #  Оверлей
    # ------------------------------------------------------------

    def _ensure_overlay(self):
        """Создаёт оверлей при первой необходимости."""
        if self._overlay is not None:
            return
        try:
            self._overlay = NightOverlay()
            self._overlay.set_max_alpha(self._intensity)
            # Растягиваем на весь экран
            screen = QApplication.primaryScreen()
            if screen:
                self._overlay.setGeometry(screen.geometry())
        except Exception as e:
            print(f"[NightMode] overlay: {e}")

    def _resize_overlay(self):
        """Подгоняет размер оверлея под экран."""
        if self._overlay is None:
            return
        screen = QApplication.primaryScreen()
        if screen:
            self._overlay.setGeometry(screen.geometry())

    # ------------------------------------------------------------
    #  API
    # ------------------------------------------------------------

    def enable(self):
        """Включить ночной режим."""
        if self._active:
            return
        self._ensure_overlay()
        self._resize_overlay()
        self._active = True
        if self._overlay:
            self._overlay.fade_to(self._intensity * 255 // 100)
        self.changed.emit(True)
        print(f"[NightMode] включён (интенсивность {self._intensity}%)")

    def disable(self):
        """Выключить ночной режим."""
        if not self._active:
            return
        self._active = False
        if self._overlay:
            self._overlay.fade_to(0)
        self.changed.emit(False)
        print("[NightMode] выключен")

    def toggle(self):
        """Переключить."""
        if self._active:
            self.disable()
        else:
            self.enable()

    def is_active(self) -> bool:
        return self._active

    # ------------------------------------------------------------
    #  Расписание
    # ------------------------------------------------------------

    def set_schedule(self, start_hour: int, end_hour: int):
        """Установить расписание: с start_hour до end_hour."""
        self._start_hour = max(0, min(23, start_hour))
        self._end_hour = max(0, min(23, end_hour))
        try:
            from ui.settings_state import state
            state().set("night_start", self._start_hour)
            state().set("night_end", self._end_hour)
        except Exception:
            pass
        self._check_schedule()

    def set_intensity(self, percent: int):
        """Установить интенсивность 0..100."""
        self._intensity = max(0, min(100, percent))
        try:
            from ui.settings_state import state
            state().set("night_intensity", self._intensity)
        except Exception:
            pass
        if self._overlay:
            self._overlay.set_max_alpha(self._intensity)
            if self._active:
                self._overlay.fade_to(self._intensity * 255 // 100)

    def set_auto(self, enabled: bool):
        """Включить/выключить авторежим по расписанию."""
        self._auto_enabled = bool(enabled)
        try:
            from ui.settings_state import state
            state().set("night_auto", self._auto_enabled)
        except Exception:
            pass
        self._check_schedule()

    # ------------------------------------------------------------
    #  Логика расписания
    # ------------------------------------------------------------

    def _is_night_now(self) -> bool:
        """Проверяет, попадает ли текущее время в ночной интервал."""
        h = datetime.now().hour
        start = self._start_hour
        end = self._end_hour

        if start == end:
            return False   # нулевой интервал

        if start < end:
            # Обычный интервал (например, 2:00–6:00)
            return start <= h < end
        else:
            # Переход через полночь (например, 21:00–07:00)
            return h >= start or h < end

    def _check_schedule(self):
        """Проверяет расписание и включает/выключает ночной режим."""
        if not self._auto_enabled:
            return
        should_be_night = self._is_night_now()
        if should_be_night and not self._active:
            self.enable()
        elif not should_be_night and self._active:
            self.disable()

    # ------------------------------------------------------------
    #  Утилиты
    # ------------------------------------------------------------

    def schedule_text(self) -> str:
        """Человекочитаемое описание расписания."""
        return f"с {self._start_hour:02d}:00 до {self._end_hour:02d}:00"

    def info(self) -> dict:
        """Полная информация о состоянии."""
        return {
            "active": self._active,
            "auto": self._auto_enabled,
            "start_hour": self._start_hour,
            "end_hour": self._end_hour,
            "intensity": self._intensity,
            "is_night_now": self._is_night_now(),
        }


# ============================================================
#  Синглтон
# ============================================================

_night_instance = None


def night() -> NightMode:
    """Возвращает глобальный менеджер ночного режима."""
    global _night_instance
    if _night_instance is None:
        _night_instance = NightMode()
    return _night_instance