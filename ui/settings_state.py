"""
Глобальное состояние настроек MountOS.
Читает из SettingsStore, при изменении — сохраняет.
"""
from PySide6.QtCore import QObject, Signal

from system.settings_store import SettingsStore
from system import paths


DEFAULTS = {
    # Оформление
    "accent":            "#6EC6FF",
    "window_opacity":    0.92,
    "window_radius":     22,
    "wallpaper":         "cosmic",
    "theme":             "dark",
    "night_auto":        True,
    "night_start":       21,
    "night_end":         7,
    "night_intensity":   45,
    "wallpaper_auto":    False,
    "wallpaper_interval": 15,
    "wallpaper_shuffle": True,

    # Интерфейс
    "show_clock":        True,
    "show_dock":         True,
    "show_welcome":      True,
    "show_startup_notification": True,
    "show_battery":      True,
    "show_cpu":          True,
    "do_not_disturb":    False,
    "quick_panel_open":  False,
    "dock_height":       90,

    # Возможности
    "blur_enabled":      True,
    "notifications_history": True,
    "hotkeys_enabled":   True,
    "hot_reload_enabled": True,

    # Язык
    "language":          "ru",
}


class SettingsState(QObject):
    changed = Signal(str, object)

    def __init__(self):
        super().__init__()
        self._store = SettingsStore(paths.SETTINGS_JSON)
        self._data = dict(DEFAULTS)

        for k, v in self._store.all().items():
            if k in DEFAULTS:
                self._data[k] = v

        self._apply_language(self._data.get("language", "ru"))

    def get(self, key, default=None):
        return self._data.get(key, default)

    def set(self, key, value):
        if self._data.get(key) == value:
            return
        self._data[key] = value
        self._store.set(key, value)
        if key == "language":
            self._apply_language(value)
        self.changed.emit(key, value)

    def all(self):
        return dict(self._data)

    def reset(self):
        self._data = dict(DEFAULTS)
        self._store._data = {}
        self._store.save()
        self._apply_language(self._data["language"])
        for k, v in DEFAULTS.items():
            self.changed.emit(k, v)

    def _apply_language(self, lang: str):
        try:
            from system.i18n import set_language
            set_language(lang)
        except Exception as e:
            print(f"[SettingsState] язык: {e}")


_state = None


def state() -> SettingsState:
    global _state
    if _state is None:
        _state = SettingsState()
    return _state