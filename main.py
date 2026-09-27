"""
MountOS — точка входа.
Первым делом изолируем окружение, потом запускаем GUI.
"""
import sys
import os

# ============================================================
#  ⚠️ КРИТИЧНО: изоляция ДО всех импортов
# ============================================================

# 1. BASE_DIR для sys.path
if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# 2. Отключаем .pyc
sys.dont_write_bytecode = True

# 3. GPU-ускорение Chromium ДО PySide6
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", (
    "--enable-gpu-rasterization "
    "--enable-zero-copy "
    "--enable-accelerated-2d-canvas "
    "--ignore-gpu-blocklist "
    "--enable-features=VaapiVideoDecoder,CanvasOopRasterization,UseSkiaRenderer "
    "--disable-features=CalculateNativeWinOcclusion,UseChromeOSDirectVideoDecoder "
    "--disable-background-timer-throttling "
    "--disable-renderer-backgrounding "
    "--disable-backgrounding-occluded-windows"
))

# 4. Настройки Qt ДО PySide6
from system.qt_config import configure_qt
configure_qt()

# 5. Изоляция окружения
from system.paths import isolate_environment, ensure_structure, info
isolate_environment()
ensure_structure()

# 6. Логирование
from system.logger import log, install_excepthook, rotate_logs
rotate_logs()
install_excepthook()

# ============================================================
#  Теперь можно импортировать PySide6
# ============================================================

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont
from PySide6.QtCore import QTimer


def _warmup_webengine():
    try:
        from PySide6.QtWebEngineCore import QWebEngineProfile
        QWebEngineProfile.defaultProfile()
        log().info("Chromium прогрет")
    except Exception as e:
        log().warn(f"Прогрев Chromium: {e}")


def main():
    log().info("=" * 60)
    log().info("MountOS запускается")
    for k, v in info().items():
        log().info(f"  {k}: {v}")

    app = QApplication(sys.argv)
    app.setApplicationName("MountOS")
    app.setOrganizationName("MountOS")
    app.setApplicationVersion("1.0")
    app.setStyle("Fusion")

    from system.qt_config import find_best_font, load_mountos_fonts
    loaded = load_mountos_fonts()
    if loaded:
        log().info(f"Загружено своих шрифтов: {loaded}")

    font_name = find_best_font()
    app.setFont(QFont(font_name, 10))
    log().info(f"Шрифт интерфейса: {font_name}")

    from ui.settings_state import state
    st = state()
    log().info(f"Настройки: accent={st.get('accent')}, wallpaper={st.get('wallpaper')}")

    from system.notify_history import history
    h = history()
    log().info(f"История уведомлений: {len(h)} записей")

    from ui.desktop import Desktop
    desktop = Desktop(BASE_DIR)
    desktop.showFullScreen()

    QTimer.singleShot(2000, _warmup_webengine)

    log().info("Горячие клавиши:")
    try:
        from ui.hotkeys import HOTKEYS_HELP
        for k, v in HOTKEYS_HELP:
            log().info(f"  {k:18} — {v}")
    except Exception:
        pass

    log().info("MountOS готов")
    sys.exit(app.exec())


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log().error("Критическая ошибка запуска", e)
        raise