"""
MountOS — Горячие клавиши.

Работают глобально в пределах окна MountOS:
  • Ctrl+Space         — Spotlight (глобальный поиск)
  • Ctrl+Alt+T         — Терминал
  • Ctrl+Alt+F         — Проводник
  • Ctrl+Alt+N         — Заметки
  • Ctrl+Alt+S         — Настройки
  • Ctrl+Alt+K         — Калькулятор
  • Ctrl+Alt+D         — Календарь
  • Ctrl+Alt+M         — Меню приложений
  • Ctrl+Alt+C         — Центр уведомлений
  • Meta (Win)         — Меню приложений
  • Alt+Tab            — следующее окно
  • Alt+Shift+Tab      — предыдущее окно
  • Meta+M             — Свернуть все окна
  • Meta+W             — Закрыть все окна
  • Esc                — Закрыть всплывающее окно
"""
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QShortcut, QKeySequence
from PySide6.QtCore import Qt, QObject


class HotkeyManager(QObject):
    """Управляет всеми горячими клавишами MountOS."""

    def __init__(self, host):
        super().__init__(host)
        self.host = host
        self._shortcuts = []
        self._alt_tab_last = 0

        self._install()

    # ------------------------------------------------------------
    #  Установка горячих клавиш
    # ------------------------------------------------------------

    def _add(self, sequence: str, callback):
        sc = QShortcut(QKeySequence(sequence), self.host)
        sc.setContext(Qt.ApplicationShortcut)
        sc.activated.connect(callback)
        self._shortcuts.append(sc)
        return sc

    def _install(self):
        # ---- Spotlight ----
        self._add("Ctrl+Space", self._on_spotlight)

        # ---- Открытие приложений ----
        self._add("Ctrl+Alt+T", lambda: self._open("terminal"))
        self._add("Ctrl+Alt+F", lambda: self._open("files"))
        self._add("Ctrl+Alt+N", lambda: self._open("notes"))
        self._add("Ctrl+Alt+S", lambda: self._open("settings"))
        self._add("Ctrl+Alt+K", lambda: self._open("calculator"))
        self._add("Ctrl+Alt+D", lambda: self._open("calendar"))

        # ---- Меню приложений ----
        self._add("Ctrl+Alt+M", self._on_app_menu)
        self._add("Meta", self._on_app_menu)

        # ---- Центр уведомлений ----
        self._add("Ctrl+Alt+C", self._on_notif_center)

        # ---- Управление окнами ----
        self._add("Alt+Tab", self._on_alt_tab)
        self._add("Alt+Shift+Tab", self._on_alt_tab_reverse)
        self._add("Meta+M", self._on_minimize_all)
        self._add("Meta+W", self._on_close_all)

        # ---- Esc — закрывает всплывающие окна ----
        self._add("Esc", self._on_escape)

    # ------------------------------------------------------------
    #  Обработчики
    # ------------------------------------------------------------

    def _on_spotlight(self):
        spot = getattr(self.host, "spotlight", None)
        if spot:
            spot.toggle()

    def _on_app_menu(self):
        menu = getattr(self.host, "app_menu", None)
        if menu:
            menu.toggle()

    def _on_notif_center(self):
        center = getattr(self.host, "notif_center", None)
        if center:
            center.toggle()

    def _open(self, app_id: str):
        if hasattr(self.host, "open_app"):
            self.host.open_app(app_id)

    # ---- Alt+Tab ----

    def _windows_list(self):
        w = getattr(self.host, "windows", [])
        return [x for x in w if x.isVisible()]

    def _on_alt_tab(self):
        wins = self._windows_list()
        if len(wins) < 2:
            return
        self._alt_tab_last = (self._alt_tab_last + 1) % len(wins)
        self._focus(wins[self._alt_tab_last])

    def _on_alt_tab_reverse(self):
        wins = self._windows_list()
        if len(wins) < 2:
            return
        self._alt_tab_last = (self._alt_tab_last - 1) % len(wins)
        self._focus(wins[self._alt_tab_last])

    def _focus(self, win):
        try:
            if win.isMinimized():
                win.showNormal()
            win.raise_()
            win.activateWindow()
        except RuntimeError:
            pass

    # ---- Win+M / Win+W ----

    def _on_minimize_all(self):
        for w in self._windows_list():
            try:
                w.showMinimized()
            except RuntimeError:
                pass

    def _on_close_all(self):
        for w in list(getattr(self.host, "windows", [])):
            try:
                w.close()
            except RuntimeError:
                pass

    # ---- Esc ----

    def _on_escape(self):
        spot = getattr(self.host, "spotlight", None)
        if spot and getattr(spot, "_visible", False):
            spot.hide_spotlight()
            return

        menu = getattr(self.host, "app_menu", None)
        if menu and getattr(menu, "_visible", False):
            menu.hide_menu()
            return

        center = getattr(self.host, "notif_center", None)
        if center and getattr(center, "_visible", False):
            center.hide_panel()
            return


# ============================================================
#  Справка
# ============================================================

HOTKEYS_HELP = [
    ("Ctrl+Space",       "Глобальный поиск (Spotlight)"),
    ("Ctrl+Alt+T",       "Терминал"),
    ("Ctrl+Alt+F",       "Проводник"),
    ("Ctrl+Alt+N",       "Заметки"),
    ("Ctrl+Alt+S",       "Настройки"),
    ("Ctrl+Alt+K",       "Калькулятор"),
    ("Ctrl+Alt+D",       "Календарь"),
    ("Ctrl+Alt+M",       "Меню приложений"),
    ("Ctrl+Alt+C",       "Центр уведомлений"),
    ("Meta (Win)",       "Меню приложений"),
    ("Alt+Tab",          "Переключение окон"),
    ("Alt+Shift+Tab",    "Переключение окон (обратно)"),
    ("Meta+M",           "Свернуть все окна"),
    ("Meta+W",           "Закрыть все окна"),
    ("Esc",              "Закрыть всплывающее окно"),
]