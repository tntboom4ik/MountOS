"""
MountOS — Локализация (i18n).

Простая система переводов:
  - tr("key") → строка на текущем языке
  - set_language("ru" | "en")
  - current_language()

Статусы языков:
  - "stable" — язык полностью переведён
  - "beta"   — язык в разработке (часть строк на английском)
"""

from PySide6.QtCore import QObject, Signal


# ============================================================
#  Статусы языков
# ============================================================

LANGUAGE_INFO = {
    "ru": {"name": "Русский",  "flag": "🇷🇺", "status": "stable"},
    "en": {"name": "English",  "flag": "🇬🇧", "status": "beta"},
}

STATUS_LABELS = {
    "ru": {
        "stable": "",
        "beta":   "Beta",
    },
    "en": {
        "stable": "",
        "beta":   "Beta",
    },
}


# ============================================================
#  Словари
# ============================================================

TRANSLATIONS = {
    "ru": {
        # ---- Общее ----
        "app.name":                    "MountOS",
        "app.welcome":                 "Добро пожаловать в MountOS",
        "common.ok":                   "ОК",
        "common.cancel":               "Отмена",
        "common.yes":                  "Да",
        "common.no":                   "Нет",
        "common.save":                 "Сохранить",
        "common.delete":               "Удалить",
        "common.close":                "Закрыть",
        "common.open":                 "Открыть",
        "common.apply":                "Применить",
        "common.reset":                "Сбросить",
        "common.error":                "Ошибка",
        "common.warning":              "Предупреждение",
        "common.success":              "Готово",
        "common.beta":                 "Бета",

        # ---- Приложения ----
        "app.files":                   "Проводник",
        "app.terminal":                "Терминал",
        "app.notes":                   "Заметки",
        "app.settings":                "Настройки",
        "app.calculator":              "Калькулятор",
        "app.gallery":                 "Галерея",
        "app.music":                   "Музыка",
        "app.taskmgr":                 "Диспетчер задач",
        "app.clock":                   "Часы",
        "app.calendar":                "Календарь",
        "app.editor":                  "Текстовый редактор",

        # ---- Настройки ----
        "settings.title":              "Настройки",
        "settings.section.about":      "Об устройстве",
        "settings.section.appearance": "Оформление",
        "settings.section.wallpaper":  "Обои",
        "settings.section.language":   "Язык",
        "settings.section.apps":       "Приложения",
        "settings.section.system":     "Система",
        "settings.section.hotkeys":    "Горячие клавиши",

        "settings.about.version":      "версия {v} «{c}»",
        "settings.about.system":       "Система",
        "settings.about.python":       "Python",
        "settings.about.pyside":       "PySide6",
        "settings.about.kernel":       "Ядро MountOS",
        "settings.about.shell":        "Оболочка",
        "settings.about.arch":         "Архитектура",
        "settings.about.host":         "Имя хоста",
        "settings.about.platform":     "Платформа",

        "settings.appearance.accent":  "Цвет акцента",
        "settings.appearance.accent_hint": "Меняет цвет активных приложений, кнопок и логотипа.",
        "settings.appearance.windows": "Окна",
        "settings.appearance.opacity": "Прозрачность",
        "settings.appearance.opacity_hint": "Насколько окна пропускают фон.",
        "settings.appearance.radius":  "Скругление углов",
        "settings.appearance.radius_hint": "Радиус углов стеклянных окон.",
        "settings.appearance.interface": "Интерфейс",
        "settings.appearance.clock":   "Показывать часы в панели",
        "settings.appearance.dock":    "Показывать док",
        "settings.appearance.welcome": "Показывать приветствие",
        "settings.appearance.blur":    "Размытие окон (Acrylic)",
        "settings.appearance.blur_hint": "Матовое стекло поверх окна.",

        "settings.wallpaper.title":    "Обои рабочего стола",
        "settings.wallpaper.hint":     "Выбери градиентную тему фона.",
        "settings.wallpaper.startup":  "Поведение при запуске",
        "settings.wallpaper.notif":    "Показывать уведомление",
        "settings.wallpaper.cosmic":   "Космический градиент",
        "settings.wallpaper.mountains":"Горный туман",
        "settings.wallpaper.neon":     "Неон",
        "settings.wallpaper.aurora":   "Аврора",

        "settings.apps.actions":       "Действия",
        "settings.apps.install_hint":  "Установи .py-приложение MountOS.",
        "settings.apps.install":       "Установить .py",
        "settings.apps.refresh":       "Обновить список",
        "settings.apps.list":          "Установленные приложения",
        "settings.apps.delete_hint":   "Пользовательские можно удалить.",
        "settings.apps.builtin":       "системное",
        "settings.apps.custom":        "пользовательское",
        "settings.apps.none":          "Приложений пока нет.",
        "settings.apps.registry_error":"Не удалось получить доступ к реестру приложений.",
        "settings.apps.delete_title":  "Удаление приложения",
        "settings.apps.delete_q":      "Удалить «{name}»?",
        "settings.apps.delete_ok":     "Приложение удалено",
        "settings.apps.install_title": "Установить приложение MountOS",
        "settings.apps.installed_ok":  "Приложение «{name}» установлено.",

        "settings.language.title":     "Язык системы",
        "settings.language.hint":      "Выбери язык интерфейса. Применяется сразу.",
        "settings.language.beta_note": "Английский язык находится в разработке. Часть строк всё ещё на русском.",

        "settings.hotkeys.title":      "Горячие клавиши",
        "settings.hotkeys.hint":       "Все комбинации работают глобально в MountOS.",

        "settings.system.state":       "Состояние",
        "settings.system.uptime":      "Аптайм MountOS",
        "settings.system.apps_count":  "Приложений в системе",
        "settings.system.windows":     "Открытых окон",
        "settings.system.control":     "Управление",
        "settings.system.restart_hint":"Перезапусти MountOS.",
        "settings.system.restart":     "Перезапустить MountOS",
        "settings.system.quit":        "Выйти из MountOS",
        "settings.system.reset_title": "Сбросить настройки",
        "settings.system.reset_q":     "Сбросить ВСЕ настройки MountOS?",
        "settings.system.reset_ok":    "Настройки сброшены",

        # ---- Остальное ----
        "notif.center_title":          "Уведомления",
        "notif.empty":                 "Уведомлений пока нет",
        "notif.mark_all_read":         "Прочитать все",
        "notif.clear":                 "Очистить",
        "notif.app_installed":         "Приложение установлено",
        "notif.app_removed":           "Приложение удалено",
        "notif.file_saved":            "Файл сохранён",
        "notif.loaded_apps":           "Загружено приложений: {n}",
        "notif.mountos":               "MountOS",

        "dock.cannot_delete_builtin":  "Нельзя удалить — системное",
    },

    "en": {
        # ---- Common ----
        "app.name":                    "MountOS",
        "app.welcome":                 "Welcome to MountOS",
        "common.ok":                   "OK",
        "common.cancel":               "Cancel",
        "common.yes":                  "Yes",
        "common.no":                   "No",
        "common.save":                 "Save",
        "common.delete":               "Delete",
        "common.close":                "Close",
        "common.open":                 "Open",
        "common.apply":                "Apply",
        "common.reset":                "Reset",
        "common.error":                "Error",
        "common.warning":              "Warning",
        "common.success":              "Done",
        "common.beta":                 "Beta",

        # ---- Apps ----
        "app.files":                   "Files",
        "app.terminal":                "Terminal",
        "app.notes":                   "Notes",
        "app.settings":                "Settings",
        "app.calculator":              "Calculator",
        "app.gallery":                 "Gallery",
        "app.music":                   "Music",
        "app.taskmgr":                 "Task Manager",
        "app.clock":                   "Clock",
        "app.calendar":                "Calendar",
        "app.editor":                  "Text Editor",

        # ---- Settings ----
        "settings.title":              "Settings",
        "settings.section.about":      "About",
        "settings.section.appearance": "Appearance",
        "settings.section.wallpaper":  "Wallpaper",
        "settings.section.language":   "Language",
        "settings.section.apps":       "Apps",
        "settings.section.system":     "System",
        "settings.section.hotkeys":    "Hotkeys",

        "settings.about.version":      "version {v} “{c}”",
        "settings.about.system":       "System",
        "settings.about.python":       "Python",
        "settings.about.pyside":       "PySide6",
        "settings.about.kernel":       "MountOS Kernel",
        "settings.about.shell":        "Shell",
        "settings.about.arch":         "Architecture",
        "settings.about.host":         "Hostname",
        "settings.about.platform":     "Platform",

        "settings.appearance.accent":  "Accent color",
        "settings.appearance.accent_hint": "Changes the color of active apps, buttons and logo.",
        "settings.appearance.windows": "Windows",
        "settings.appearance.opacity": "Opacity",
        "settings.appearance.opacity_hint": "How much the windows let through.",
        "settings.appearance.radius":  "Corner radius",
        "settings.appearance.radius_hint": "Radius of glass window corners.",
        "settings.appearance.interface": "Interface",
        "settings.appearance.clock":   "Show clock in panel",
        "settings.appearance.dock":    "Show dock",
        "settings.appearance.welcome": "Show welcome message",
        "settings.appearance.blur":    "Window blur (Acrylic)",
        "settings.appearance.blur_hint": "Matte glass behind the window.",

        "settings.wallpaper.title":    "Desktop wallpaper",
        "settings.wallpaper.hint":     "Choose a gradient background theme.",
        "settings.wallpaper.startup":  "Startup behavior",
        "settings.wallpaper.notif":    "Show notification",
        "settings.wallpaper.cosmic":   "Cosmic gradient",
        "settings.wallpaper.mountains":"Mountain mist",
        "settings.wallpaper.neon":     "Neon",
        "settings.wallpaper.aurora":   "Aurora",

        "settings.apps.actions":       "Actions",
        "settings.apps.install_hint":  "Install a MountOS .py app.",
        "settings.apps.install":       "Install .py",
        "settings.apps.refresh":       "Refresh list",
        "settings.apps.list":          "Installed apps",
        "settings.apps.delete_hint":   "User apps can be removed.",
        "settings.apps.builtin":       "built-in",
        "settings.apps.custom":        "user",
        "settings.apps.none":          "No apps yet.",
        "settings.apps.registry_error":"Could not access the app registry.",
        "settings.apps.delete_title":  "Uninstall app",
        "settings.apps.delete_q":      "Delete “{name}”?",
        "settings.apps.delete_ok":     "App removed",
        "settings.apps.install_title": "Install MountOS app",
        "settings.apps.installed_ok":  "App “{name}” installed.",

        "settings.language.title":     "System language",
        "settings.language.hint":      "Choose the interface language. Applied instantly.",
        "settings.language.beta_note": "English is under development. Some strings are still in Russian.",

        "settings.hotkeys.title":      "Hotkeys",
        "settings.hotkeys.hint":       "All combinations work globally within MountOS.",

        "settings.system.state":       "Status",
        "settings.system.uptime":      "MountOS uptime",
        "settings.system.apps_count":  "Apps installed",
        "settings.system.windows":     "Open windows",
        "settings.system.control":     "Control",
        "settings.system.restart_hint":"Restart MountOS.",
        "settings.system.restart":     "Restart MountOS",
        "settings.system.quit":        "Quit MountOS",
        "settings.system.reset_title": "Reset settings",
        "settings.system.reset_q":     "Reset ALL MountOS settings?",
        "settings.system.reset_ok":    "Settings reset",

        # ---- Rest ----
        "notif.center_title":          "Notifications",
        "notif.empty":                 "No notifications yet",
        "notif.mark_all_read":         "Mark all read",
        "notif.clear":                 "Clear",
        "notif.app_installed":         "App installed",
        "notif.app_removed":           "App removed",
        "notif.file_saved":            "File saved",
        "notif.loaded_apps":           "Apps loaded: {n}",
        "notif.mountos":               "MountOS",

        "dock.cannot_delete_builtin":  "Cannot delete — built-in",
    },
}


# ============================================================
#  Ядро
# ============================================================

class _I18N(QObject):
    language_changed = Signal(str)

    def __init__(self):
        super().__init__()
        self._lang = "ru"

    def language(self) -> str:
        return self._lang

    def set_language(self, lang: str):
        if lang not in TRANSLATIONS:
            lang = "ru"
        if self._lang == lang:
            return
        self._lang = lang
        self.language_changed.emit(lang)

    def tr(self, key: str, **kwargs) -> str:
        table = TRANSLATIONS.get(self._lang, {})
        text = table.get(key)
        if text is None:
            text = TRANSLATIONS.get("en", {}).get(key, key)
        if kwargs:
            try:
                text = text.format(**kwargs)
            except Exception:
                pass
        return text

    def available_languages(self):
        """[(code, name, flag, status)]"""
        result = []
        for code, info in LANGUAGE_INFO.items():
            result.append((code, info["name"], info["flag"], info["status"]))
        return result


_instance = None


def _i18n() -> _I18N:
    global _instance
    if _instance is None:
        _instance = _I18N()
    return _instance


# ============================================================
#  Публичный API
# ============================================================

def tr(key: str, **kwargs) -> str:
    return _i18n().tr(key, **kwargs)


def set_language(lang: str):
    _i18n().set_language(lang)


def current_language() -> str:
    return _i18n().language()


def available_languages():
    """
    Список (код, имя, флаг, статус).
    Статус: "stable" или "beta".
    """
    return _i18n().available_languages()


def language_status(lang: str = None) -> str:
    """Возвращает 'stable' или 'beta' для указанного языка (или текущего)."""
    if lang is None:
        lang = current_language()
    info = LANGUAGE_INFO.get(lang)
    if info is None:
        return "stable"
    return info.get("status", "stable")


def is_beta(lang: str = None) -> bool:
    return language_status(lang) == "beta"


def on_change(callback):
    _i18n().language_changed.connect(callback)


def language_signal():
    return _i18n().language_changed