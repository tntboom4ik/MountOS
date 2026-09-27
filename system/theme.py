"""
MountOS — Система тем.

Поддерживает:
  • Тёмная тема (по умолчанию)
  • Светлая тема
  • Ночной режим (тёплый фильтр после 21:00)
  • Кастомные палитры

Доступные цвета:
    theme.get("text_primary")      → "#FFFFFF"
    theme.get("window_bg")          → (28, 34, 54, 235) — RGBA кортеж
    theme.get("panel_bg")           → "rgba(255, 255, 255, 0.06)"

Использование:
    from system.theme import theme
    color = theme.get("text_primary")
    
    # Или прямой доступ:
    from system.theme import theme
    bg_rgba = theme.color_tuple("window_bg")
"""

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QColor


# ============================================================
#  Палитры тем
# ============================================================

THEMES = {
    # ═══════════════════════════════════════════════════════
    #  Тёмная — основная (Liquid Glass)
    # ═══════════════════════════════════════════════════════
    "dark": {
        "name":               "Тёмная",

        # Окна
        "window_bg":          (28, 34, 54, 235),       # RGBA
        "window_border":      (255, 255, 255, 50),
        "window_highlight":   (255, 255, 255, 30),

        # Панели и доки
        "panel_bg":           "rgba(255, 255, 255, 0.06)",
        "panel_border":       "rgba(255, 255, 255, 0.10)",
        "dock_bg":            "rgba(255, 255, 255, 0.08)",
        "dock_border":        "rgba(255, 255, 255, 0.16)",

        # Текст
        "text_primary":       "#FFFFFF",
        "text_secondary":     "rgba(255, 255, 255, 0.75)",
        "text_tertiary":      "rgba(255, 255, 255, 0.45)",
        "text_disabled":      "rgba(255, 255, 255, 0.30)",

        # Поля ввода
        "input_bg":           "rgba(255, 255, 255, 0.08)",
        "input_border":       "rgba(255, 255, 255, 0.15)",
        "input_focus_border": "rgba(110, 198, 255, 0.65)",

        # Специальные
        "shadow":             (0, 0, 0, 180),
        "hover_bg":           "rgba(255, 255, 255, 0.10)",
        "active_bg":          "rgba(110, 198, 255, 0.25)",
        "danger":             "#FF6B8A",
        "success":            "#6EE7B7",
        "warning":            "#FFB86C",

        # Обои по умолчанию
        "wallpaper_default":  "cosmic",
    },

    # ═══════════════════════════════════════════════════════
    #  Светлая
    # ═══════════════════════════════════════════════════════
    "light": {
        "name":               "Светлая",

        # Окна
        "window_bg":          (248, 250, 255, 245),
        "window_border":      (0, 0, 0, 40),
        "window_highlight":   (255, 255, 255, 220),

        # Панели и доки
        "panel_bg":           "rgba(255, 255, 255, 0.65)",
        "panel_border":       "rgba(0, 0, 0, 0.10)",
        "dock_bg":            "rgba(255, 255, 255, 0.70)",
        "dock_border":        "rgba(0, 0, 0, 0.12)",

        # Текст
        "text_primary":       "#1A1F35",
        "text_secondary":     "rgba(26, 31, 53, 0.75)",
        "text_tertiary":      "rgba(26, 31, 53, 0.50)",
        "text_disabled":      "rgba(26, 31, 53, 0.30)",

        # Поля ввода
        "input_bg":           "rgba(0, 0, 0, 0.05)",
        "input_border":       "rgba(0, 0, 0, 0.15)",
        "input_focus_border": "rgba(110, 198, 255, 0.90)",

        # Специальные
        "shadow":             (0, 0, 0, 60),
        "hover_bg":           "rgba(0, 0, 0, 0.06)",
        "active_bg":          "rgba(110, 198, 255, 0.30)",
        "danger":             "#D63A5B",
        "success":            "#2AA876",
        "warning":            "#D68A2A",

        # Обои по умолчанию
        "wallpaper_default":  "light_mountains",
    },
}


# ============================================================
#  Менеджер тем
# ============================================================

class ThemeManager(QObject):
    """
    Синглтон-менеджер тем MountOS.
    Эмитит signal при смене темы.
    """

    changed = Signal(str)   # имя новой темы

    def __init__(self):
        super().__init__()
        self._current_name = "dark"   # по умолчанию
        self._connected = False

        # Подключаемся к настройкам (если state уже создан)
        self._connect_to_settings()

    def _connect_to_settings(self):
        """Подписывается на изменения в settings_state."""
        if self._connected:
            return
        try:
            from ui.settings_state import state
            st = state()
            # Читаем текущую тему из настроек
            saved_theme = st.get("theme", "dark")
            if saved_theme in THEMES:
                self._current_name = saved_theme
            # Подписываемся
            st.changed.connect(self._on_settings_changed)
            self._connected = True
        except Exception as e:
            print(f"[Theme] не удалось подключиться к settings: {e}")

    def _on_settings_changed(self, key, value):
        if key == "theme" and value in THEMES:
            self.set_theme(value, save=False)

    # ------------------------------------------------------------
    #  Публичный API
    # ------------------------------------------------------------

    def current_name(self) -> str:
        """Имя текущей темы."""
        return self._current_name

    def current(self) -> dict:
        """Словарь с цветами текущей темы."""
        return THEMES.get(self._current_name, THEMES["dark"])

    def set_theme(self, name: str, save: bool = True):
        """
        Устанавливает тему.
        save=True — также сохраняет в settings.json.
        """
        if name not in THEMES:
            print(f"[Theme] неизвестная тема: {name}")
            return
        if name == self._current_name:
            return
        self._current_name = name
        if save:
            try:
                from ui.settings_state import state
                state().set("theme", name)
            except Exception:
                pass
        self.changed.emit(name)

    def toggle(self):
        """Переключает тёмная ↔ светлая."""
        new = "light" if self._current_name == "dark" else "dark"
        self.set_theme(new)

    # ------------------------------------------------------------
    #  Получение цветов
    # ------------------------------------------------------------

    def get(self, key: str, default=None):
        """Возвращает значение по ключу."""
        return self.current().get(key, default)

    def color(self, key: str, default: str = "#FFFFFF") -> QColor:
        """Возвращает QColor по ключу."""
        val = self.get(key, default)
        if isinstance(val, tuple):
            r, g, b, a = val
            return QColor(r, g, b, a)
        if isinstance(val, str):
            return QColor(val)
        return QColor(default)

    def color_tuple(self, key: str, default=(255, 255, 255, 255)):
        """Возвращает RGBA-кортеж по ключу."""
        val = self.get(key, default)
        if isinstance(val, tuple):
            return val
        if isinstance(val, str):
            c = QColor(val)
            return (c.red(), c.green(), c.blue(), c.alpha())
        return default

    def rgba_string(self, key: str, default="rgba(255,255,255,0.5)") -> str:
        """Возвращает строку rgba(...) по ключу."""
        val = self.get(key, default)
        if isinstance(val, str):
            return val
        if isinstance(val, tuple):
            r, g, b, a = val
            return f"rgba({r}, {g}, {b}, {a/255:.3f})"
        return default

    # ------------------------------------------------------------
    #  Утилиты
    # ------------------------------------------------------------

    def is_dark(self) -> bool:
        return self._current_name == "dark"

    def is_light(self) -> bool:
        return self._current_name == "light"

    def available(self):
        """Список доступных тем: [(name, display_name), ...]"""
        return [(k, v["name"]) for k, v in THEMES.items()]

    def accent(self) -> str:
        """Акцентный цвет из настроек (не из темы)."""
        try:
            from ui.settings_state import state
            return state().get("accent", "#6EC6FF")
        except Exception:
            return "#6EC6FF"


# ============================================================
#  Синглтон
# ============================================================

_theme_instance = None


def theme() -> ThemeManager:
    """Возвращает глобальный менеджер тем (синглтон)."""
    global _theme_instance
    if _theme_instance is None:
        _theme_instance = ThemeManager()
    return _theme_instance