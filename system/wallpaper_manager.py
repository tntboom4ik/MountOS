"""
MountOS — Менеджер обоев.

Возможности:
  • 8+ встроенных градиентных обоев
  • Автосмена по таймеру (каждые N минут)
  • Пользовательские обои из VFS (/Pictures/)
  • Плавный переход между обоями
  • Случайный порядок или последовательный

Использование:
    from system.wallpaper_manager import wallpaper
    wallpaper.current_name()          # "cosmic"
    wallpaper.set("mountains")        # сменить
    wallpaper.next()                  # следующий
    wallpaper.start_auto(15)          # автосмена каждые 15 мин
    wallpaper.stop_auto()             # остановить
"""

import random

from PySide6.QtCore import QObject, Signal, QTimer
from PySide6.QtGui import QColor, QLinearGradient, QPixmap, QPainter


# ============================================================
#  Встроенные градиентные обои
# ============================================================

WALLPAPERS = {
    # ─── Тёмные ───
    "cosmic": {
        "name":   "Космический градиент",
        "theme":  "dark",
        "colors": ("#0A0E1A", "#131A2E", "#1A1F35"),
        "glow1":  (110, 198, 255),
        "glow2":  (179, 136, 255),
    },
    "mountains": {
        "name":   "Горный туман",
        "theme":  "dark",
        "colors": ("#101820", "#1F2D3A", "#354A5E"),
        "glow1":  (140, 200, 180),
        "glow2":  (200, 220, 200),
    },
    "neon": {
        "name":   "Неон",
        "theme":  "dark",
        "colors": ("#160020", "#2A0050", "#4A0080"),
        "glow1":  (255, 80, 200),
        "glow2":  (120, 100, 255),
    },
    "aurora": {
        "name":   "Аврора",
        "theme":  "dark",
        "colors": ("#021B1B", "#053B3B", "#0A5C5C"),
        "glow1":  (100, 255, 200),
        "glow2":  (150, 200, 255),
    },
    "sunset": {
        "name":   "Закат",
        "theme":  "dark",
        "colors": ("#1A0A0E", "#3D1520", "#6B2E3F"),
        "glow1":  (255, 150, 100),
        "glow2":  (255, 80, 150),
    },
    "ocean": {
        "name":   "Океан",
        "theme":  "dark",
        "colors": ("#020C1B", "#0A2540", "#0F3A5F"),
        "glow1":  (100, 180, 255),
        "glow2":  (60, 220, 220),
    },

    # ─── Светлые ───
    "light_mountains": {
        "name":   "Светлые горы",
        "theme":  "light",
        "colors": ("#E8EEF5", "#D0DCE8", "#B8C9DB"),
        "glow1":  (150, 200, 255),
        "glow2":  (200, 220, 200),
    },
    "light_clouds": {
        "name":   "Облака",
        "theme":  "light",
        "colors": ("#F5F7FA", "#E8ECF2", "#DCE2EC"),
        "glow1":  (180, 200, 255),
        "glow2":  (255, 220, 200),
    },
    "light_peach": {
        "name":   "Персик",
        "theme":  "light",
        "colors": ("#FFF5EE", "#FFE5D5", "#FFD6B8"),
        "glow1":  (255, 180, 150),
        "glow2":  (255, 220, 180),
    },
}


# ============================================================
#  Менеджер обоев
# ============================================================

class WallpaperManager(QObject):
    """
    Синглтон-менеджер обоев MountOS.
    Эмитит changed при смене обоев.
    """

    changed = Signal(str)   # имя новых обоев

    def __init__(self):
        super().__init__()
        self._current = "cosmic"
        self._auto_enabled = False
        self._auto_interval_min = 15
        self._auto_shuffle = True
        self._connected = False

        # Таймер автосмены
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_auto_tick)

        # Реакция на смену в настройках
        self._connect_to_settings()

    def _connect_to_settings(self):
        if self._connected:
            return
        try:
            from ui.settings_state import state
            st = state()
            self._current = st.get("wallpaper", "cosmic")
            self._auto_enabled = st.get("wallpaper_auto", False)
            self._auto_interval_min = st.get("wallpaper_interval", 15)
            self._auto_shuffle = st.get("wallpaper_shuffle", True)
            st.changed.connect(self._on_settings_changed)
            self._connected = True

            # Если автосмена была включена — запускаем
            if self._auto_enabled:
                self.start_auto(self._auto_interval_min, self._auto_shuffle)
        except Exception as e:
            print(f"[Wallpaper] settings connection: {e}")

    def _on_settings_changed(self, key, value):
        if key == "wallpaper" and value in WALLPAPERS:
            if value != self._current:
                self._current = value
                self.changed.emit(value)
        elif key == "wallpaper_auto":
            if value and not self._auto_enabled:
                self.start_auto(self._auto_interval_min, self._auto_shuffle)
            elif not value and self._auto_enabled:
                self.stop_auto()
        elif key == "wallpaper_interval":
            self._auto_interval_min = max(1, int(value))
            if self._auto_enabled:
                self.start_auto(self._auto_interval_min, self._auto_shuffle)
        elif key == "wallpaper_shuffle":
            self._auto_shuffle = bool(value)

    # ------------------------------------------------------------
    #  Основной API
    # ------------------------------------------------------------

    def current_name(self) -> str:
        return self._current

    def current(self) -> dict:
        return WALLPAPERS.get(self._current, WALLPAPERS["cosmic"])

    def set(self, name: str, save: bool = True):
        """Установить обои по имени."""
        if name not in WALLPAPERS:
            print(f"[Wallpaper] неизвестные обои: {name}")
            return
        if name == self._current:
            return
        self._current = name
        if save:
            try:
                from ui.settings_state import state
                state().set("wallpaper", name)
            except Exception:
                pass
        self.changed.emit(name)

    def next(self):
        """Следующие обои (по порядку)."""
        names = list(WALLPAPERS.keys())
        idx = names.index(self._current) if self._current in names else 0
        nxt = names[(idx + 1) % len(names)]
        self.set(nxt)

    def prev(self):
        """Предыдущие обои (по порядку)."""
        names = list(WALLPAPERS.keys())
        idx = names.index(self._current) if self._current in names else 0
        prv = names[(idx - 1) % len(names)]
        self.set(prv)

    def random(self):
        """Случайные обои."""
        names = list(WALLPAPERS.keys())
        if len(names) <= 1:
            return
        cur = self._current
        # Избегаем повтора
        pool = [n for n in names if n != cur]
        self.set(random.choice(pool))

    def available(self):
        """Список всех обоев: [(name, display_name), ...]"""
        return [(k, v["name"]) for k, v in WALLPAPERS.items()]

    def available_for_theme(self, theme_name: str):
        """Обои, подходящие под тему (dark/light)."""
        return [(k, v["name"]) for k, v in WALLPAPERS.items()
                if v.get("theme") == theme_name]

    # ------------------------------------------------------------
    #  Автосмена
    # ------------------------------------------------------------

    def start_auto(self, interval_min: int = 15, shuffle: bool = True):
        """
        Запустить автосмену обоев.
        interval_min — интервал в минутах (минимум 1).
        shuffle — если True, обои случайные; иначе по порядку.
        """
        self._auto_interval_min = max(1, int(interval_min))
        self._auto_shuffle = bool(shuffle)
        self._auto_enabled = True

        # QTimer работает в миллисекундах
        ms = self._auto_interval_min * 60 * 1000
        self._timer.start(ms)

        # Сохраняем в настройки
        try:
            from ui.settings_state import state
            state().set("wallpaper_auto", True)
            state().set("wallpaper_interval", self._auto_interval_min)
            state().set("wallpaper_shuffle", self._auto_shuffle)
        except Exception:
            pass

        print(f"[Wallpaper] автосмена: каждые {self._auto_interval_min} мин, "
              f"{'случайно' if self._auto_shuffle else 'по порядку'}")

    def stop_auto(self):
        """Остановить автосмену."""
        self._timer.stop()
        self._auto_enabled = False
        try:
            from ui.settings_state import state
            state().set("wallpaper_auto", False)
        except Exception:
            pass
        print("[Wallpaper] автосмена остановлена")

    def is_auto_enabled(self) -> bool:
        return self._auto_enabled

    def _on_auto_tick(self):
        if self._auto_shuffle:
            self.random()
        else:
            self.next()

    # ------------------------------------------------------------
    #  Рендер превью (для настроек)
    # ------------------------------------------------------------

    def make_preview(self, name: str, width: int = 160, height: int = 100) -> QPixmap:
        """
        Создаёт превью обоев заданного размера.
        Используется в Настройках → Обои.
        """
        if name not in WALLPAPERS:
            name = "cosmic"
        wp = WALLPAPERS[name]
        colors = wp["colors"]
        g1 = wp["glow1"]
        g2 = wp["glow2"]

        pm = QPixmap(width, height)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)

        # Основной градиент
        grad = QLinearGradient(0, 0, width, height)
        grad.setColorAt(0, QColor(colors[0]))
        grad.setColorAt(0.5, QColor(colors[1]))
        grad.setColorAt(1, QColor(colors[2]))
        p.fillRect(0, 0, width, height, grad)

        # Свечение 1 (верх-лево)
        g = QLinearGradient(0, 0, width * 0.6, height * 0.6)
        g.setColorAt(0, QColor(g1[0], g1[1], g1[2], 90))
        g.setColorAt(1, QColor(g1[0], g1[1], g1[2], 0))
        p.setBrush(g)
        p.setPen(0)
        r = int(width * 0.75)
        p.drawEllipse(-int(width * 0.12), -int(height * 0.20), r, r)

        # Свечение 2 (низ-право)
        g2_ = QLinearGradient(width, height, width * 0.4, height * 0.4)
        g2_.setColorAt(0, QColor(g2[0], g2[1], g2[2], 80))
        g2_.setColorAt(1, QColor(g2[0], g2[1], g2[2], 0))
        p.setBrush(g2_)
        r2 = int(width * 0.8)
        p.drawEllipse(int(width * 0.35), int(height * 0.20), r2, r2)

        p.end()
        return pm

    def render_to_widget(self, widget, name: str = None):
        """
        Рисует обои напрямую на виджете (для desktop.py).
        widget — QWidget, на котором рисуем.
        """
        if name is None:
            name = self._current
        if name not in WALLPAPERS:
            name = "cosmic"

        from PySide6.QtGui import QPainter, QBrush
        from PySide6.QtCore import Qt

        wp = WALLPAPERS[name]
        colors = wp["colors"]
        g1 = wp["glow1"]
        g2 = wp["glow2"]

        p = QPainter(widget)
        p.setRenderHint(QPainter.Antialiasing)

        w, h = widget.width(), widget.height()

        # Основной градиент
        grad = QLinearGradient(0, 0, w, h)
        grad.setColorAt(0, QColor(colors[0]))
        grad.setColorAt(0.5, QColor(colors[1]))
        grad.setColorAt(1, QColor(colors[2]))
        p.fillRect(widget.rect(), QBrush(grad))

        # Свечение 1
        glow1 = QLinearGradient(0, 0, 600, 600)
        glow1.setColorAt(0, QColor(*g1, 40))
        glow1.setColorAt(1, QColor(*g1, 0))
        p.setBrush(QBrush(glow1))
        p.setPen(Qt.NoPen)
        p.drawEllipse(-200, -200, 900, 900)

        # Свечение 2
        glow2 = QLinearGradient(w, h, w - 700, h - 700)
        glow2.setColorAt(0, QColor(*g2, 35))
        glow2.setColorAt(1, QColor(*g2, 0))
        p.setBrush(QBrush(glow2))
        p.drawEllipse(w - 500, h - 500, 1000, 1000)

        p.end()


# ============================================================
#  Синглтон
# ============================================================

_wallpaper_instance = None


def wallpaper() -> WallpaperManager:
    """Возвращает глобальный менеджер обоев."""
    global _wallpaper_instance
    if _wallpaper_instance is None:
        _wallpaper_instance = WallpaperManager()
    return _wallpaper_instance


# ============================================================
#  Обратная совместимость со старым WALLPAPERS из settings.py
# ============================================================

def get_wallpapers_dict():
    """
    Возвращает словарь в старом формате (colors, glow1, glow2),
    чтобы apps/settings.py мог использовать его без изменений.
    """
    return {
        k: (v["colors"], v["glow1"], v["glow2"])
        for k, v in WALLPAPERS.items()
    }