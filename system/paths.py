"""
MountOS — Единая точка путей.

Все пути — ВНУТРИ папки MountOS.
Никаких обращений к системным папкам (кроме sys.executable).
Работает и на Windows, и на Linux, и на macOS.
"""
from pathlib import Path
import sys
import os


# ============================================================
#  Корень MountOS
# ============================================================

def _detect_base_dir() -> Path:
    """Корень MountOS — папка, где лежит main.py или .exe."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    else:
        return Path(__file__).resolve().parent.parent


BASE = _detect_base_dir()
"""Корень MountOS — всё лежит внутри."""


def _detect_bundle_dir() -> Path:
    """Папка со встроенными ресурсами (для PyInstaller — _MEIPASS)."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", BASE))
    return BASE


BUNDLE = _detect_bundle_dir()


# ============================================================
#  Хранилище (всё внутри MountOS/system/storage/)
# ============================================================

STORAGE = BASE / "system" / "storage"
STORAGE.mkdir(parents=True, exist_ok=True)

USER_DATA = STORAGE / "user_data"
USER_DATA.mkdir(parents=True, exist_ok=True)

TEMP_DIR = STORAGE / "temp"
TEMP_DIR.mkdir(parents=True, exist_ok=True)

HOME_DIR = USER_DATA / "home"
HOME_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
#  Логи
# ============================================================

LOGS_DIR = BASE / "system" / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)

LOG_FILE = LOGS_DIR / "mountos.log"
ERROR_LOG_FILE = LOGS_DIR / "errors.log"


# ============================================================
#  Файлы данных
# ============================================================

SETTINGS_JSON = USER_DATA / "settings.json"
DESKTOP_JSON = USER_DATA / "desktop.json"
NOTIF_HISTORY = USER_DATA / "notifications.json"


# ============================================================
#  Стандартные папки VFS
# ============================================================

DOCS_DIR = HOME_DIR / "Documents"
PICS_DIR = HOME_DIR / "Pictures"
NOTES_DIR = HOME_DIR / "Notes"
DOWNLOADS_DIR = HOME_DIR / "Downloads"
MUSIC_DIR = HOME_DIR / "Music"

for d in (DOCS_DIR, PICS_DIR, NOTES_DIR, DOWNLOADS_DIR, MUSIC_DIR):
    d.mkdir(parents=True, exist_ok=True)


# ============================================================
#  Ресурсы приложения
# ============================================================

ASSETS_DIR = BUNDLE / "assets"
FONTS_DIR = ASSETS_DIR / "fonts"
ICONS_DIR = ASSETS_DIR / "icons"

ASSETS_DIR.mkdir(parents=True, exist_ok=True)
FONTS_DIR.mkdir(parents=True, exist_ok=True)
ICONS_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
#  Приложения MountOS
# ============================================================

APPS_DIR = BUNDLE / "apps"
USER_APPS_DIR = BASE / "system" / "user_apps"
USER_APPS_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
#  Платформа (только для запуска Python)
# ============================================================

def _detect_platform() -> str:
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform.startswith("linux"):
        return "linux"
    if sys.platform.startswith("darwin"):
        return "macos"
    return "unknown"


PLATFORM = _detect_platform()
IS_WINDOWS = PLATFORM == "windows"
IS_LINUX = PLATFORM == "linux"
IS_MACOS = PLATFORM == "macos"
IS_UNKNOWN = PLATFORM == "unknown"

IS_FROZEN = getattr(sys, "frozen", False)


# ============================================================
#  Изоляция от системы
# ============================================================

def isolate_environment():
    """
    Настраивает переменные окружения так, чтобы MountOS
    не зависела от системных путей.
    """
    sys.dont_write_bytecode = True

    os.environ.setdefault("QT_PLUGIN_PATH", str(BUNDLE))

    os.environ["TEMP"] = str(TEMP_DIR)
    os.environ["TMP"] = str(TEMP_DIR)
    os.environ["TMPDIR"] = str(TEMP_DIR)

    os.environ["MOUNTOS_HOME"] = str(HOME_DIR)
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

    os.environ["PYTHONPYCACHEPREFIX"] = str(TEMP_DIR / "pycache")
    (TEMP_DIR / "pycache").mkdir(parents=True, exist_ok=True)


# ============================================================
#  Утилиты
# ============================================================

def app_data_dir(app_id: str) -> Path:
    """Папка для данных конкретного приложения."""
    d = USER_DATA / "apps" / app_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def ensure_structure():
    """Гарантирует, что все нужные папки существуют."""
    dirs = [
        STORAGE, USER_DATA, TEMP_DIR, HOME_DIR,
        LOGS_DIR,
        DOCS_DIR, PICS_DIR, NOTES_DIR, DOWNLOADS_DIR, MUSIC_DIR,
        ASSETS_DIR, FONTS_DIR, ICONS_DIR,
        USER_APPS_DIR,
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)


def info() -> dict:
    """Информация о путях."""
    return {
        "base": str(BASE),
        "bundle": str(BUNDLE),
        "storage": str(STORAGE),
        "user_data": str(USER_DATA),
        "home": str(HOME_DIR),
        "temp": str(TEMP_DIR),
        "logs": str(LOGS_DIR),
        "platform": PLATFORM,
        "frozen": IS_FROZEN,
        "python": sys.version.split()[0],
        "executable": sys.executable,
    }