"""
MountOS — Настройки Qt.
Изолирует MountOS от системных настроек Qt.
"""
import os

from system import paths


def configure_qt():
    """Вызывается из main.py ДО первого импорта PySide6."""
    os.environ.setdefault("QT_QPA_PLATFORM_PLUGIN_PATH", str(paths.BUNDLE))
    os.environ.setdefault("XDG_CACHE_HOME", str(paths.TEMP_DIR / "qt_cache"))
    (paths.TEMP_DIR / "qt_cache").mkdir(parents=True, exist_ok=True)

    os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "0")
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "0")
    os.environ.setdefault("QT_LOGGING_RULES", "*.debug=false;qt.qpa.*=false")
    os.environ.setdefault("QT_SCALE_FACTOR", "1")


def find_best_font() -> str:
    """Возвращает название шрифта, который точно есть в системе."""
    from PySide6.QtGui import QFontDatabase
    families = set(QFontDatabase.families())

    for name in (
        "Inter",
        "Segoe UI",
        "SF Pro Display",
        "Ubuntu",
        "Cantarell",
        "Noto Sans",
        "DejaVu Sans",
        "Liberation Sans",
        "Arial",
        "Helvetica",
    ):
        if name in families:
            return name

    return "sans-serif"


def find_monospace_font() -> str:
    from PySide6.QtGui import QFontDatabase
    families = set(QFontDatabase.families())

    for name in (
        "JetBrains Mono",
        "Fira Code",
        "Cascadia Code",
        "Consolas",
        "Ubuntu Mono",
        "DejaVu Sans Mono",
        "Liberation Mono",
        "Courier New",
        "monospace",
    ):
        if name in families:
            return name

    return "monospace"


def get_platform_style() -> str:
    return "Fusion"


def load_mountos_fonts() -> int:
    """Загружает свои шрифты из assets/fonts/, если они там есть."""
    from PySide6.QtGui import QFontDatabase

    font_dir = paths.FONTS_DIR
    if not font_dir.exists():
        return 0

    count = 0
    for font_file in font_dir.glob("*.ttf"):
        try:
            QFontDatabase.addApplicationFont(str(font_file))
            count += 1
        except Exception:
            pass
    for font_file in font_dir.glob("*.otf"):
        try:
            QFontDatabase.addApplicationFont(str(font_file))
            count += 1
        except Exception:
            pass

    return count