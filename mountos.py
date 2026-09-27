"""
MountOS SDK — упрощённый API для разработчиков приложений.

Пример использования в своём приложении:

    import mountos

    APP_NAME = "Моё приложение"
    APP_ICON = "globe"

    def build():
        w = mountos.QWidget()
        lay = mountos.QVBoxLayout(w)
        lay.addWidget(mountos.title_label("Привет!"))
        
        btn = mountos.accent_button("Уведомить")
        btn.clicked.connect(lambda: mountos.notify("Готово", "Работает!"))
        lay.addWidget(btn)
        
        return w
"""

from PySide6.QtWidgets import QApplication


# ============================================================
#  Внутренние хелперы
# ============================================================

def _desktop():
    """Находит главный Desktop MountOS."""
    for top in QApplication.topLevelWidgets():
        if hasattr(top, "notifications") and hasattr(top, "open_app"):
            return top
        ref = getattr(top, "desktop_ref", None)
        if ref is not None and hasattr(ref, "notifications"):
            return ref
        for child in top.findChildren(object):
            ref = getattr(child, "desktop_ref", None)
            if ref is not None and hasattr(ref, "notifications"):
                return ref
    return None


# ============================================================
#  Уведомления
# ============================================================

def notify(title: str, text: str = "", duration_ms: int = 3200) -> bool:
    """Показать всплывающее уведомление."""
    d = _desktop()
    if d and hasattr(d, "notifications"):
        try:
            d.notifications.push(title, text, duration_ms=duration_ms)
            return True
        except TypeError:
            d.notifications.push(title, text)
            return True
    return False


# ============================================================
#  Настройки
# ============================================================

def settings():
    """Возвращает объект настроек MountOS."""
    from ui.settings_state import state
    return state()


def accent_color() -> str:
    """Текущий акцентный цвет в hex."""
    return settings().get("accent", "#6EC6FF")


# ============================================================
#  Виртуальная файловая система
# ============================================================

class _FS:
    """Доступ к VFS MountOS (песочница в system/user_data/home/)."""

    def _vfs(self):
        d = _desktop()
        return getattr(d, "vfs", None) if d else None

    def read(self, path: str, default: str = "") -> str:
        v = self._vfs()
        return v.read_text(path, default) if v else default

    def write(self, path: str, text: str) -> bool:
        v = self._vfs()
        if v:
            v.write_text(path, text)
            return True
        return False

    def read_bytes(self, path: str) -> bytes:
        v = self._vfs()
        return v.read_bytes(path) if v else b""

    def write_bytes(self, path: str, data: bytes) -> bool:
        v = self._vfs()
        if v:
            v.write_bytes(path, data)
            return True
        return False

    def exists(self, path: str) -> bool:
        v = self._vfs()
        return v.exists(path) if v else False

    def is_dir(self, path: str) -> bool:
        v = self._vfs()
        return v.is_dir(path) if v else False

    def list(self, path: str = "/"):
        v = self._vfs()
        return v.listdir(path) if v else []

    def mkdir(self, path: str):
        v = self._vfs()
        if v:
            v.mkdir(path)

    def delete(self, path: str):
        v = self._vfs()
        if v:
            v.delete(path)

    def copy(self, src: str, dst: str):
        v = self._vfs()
        if v:
            v.copy(src, dst)

    def rename(self, old: str, new: str):
        v = self._vfs()
        if v:
            v.rename(old, new)

    def home(self) -> str:
        return "/"

    def join(self, *parts) -> str:
        v = self._vfs()
        return v.join(*parts) if v else "/" + "/".join(p.strip("/") for p in parts)

    def basename(self, path: str) -> str:
        v = self._vfs()
        return v.basename(path) if v else path.split("/")[-1]

    def parent(self, path: str) -> str:
        v = self._vfs()
        return v.parent(path) if v else "/"


fs = _FS()


# ============================================================
#  Работа с окнами и приложениями
# ============================================================

def open_app(app_id: str) -> bool:
    """Открыть приложение по его app_id."""
    d = _desktop()
    if d and hasattr(d, "open_app"):
        d.open_app(app_id)
        return True
    return False


def open_file(path: str) -> bool:
    """Открыть файл в просмотрщике MountOS."""
    d = _desktop()
    if d and hasattr(d, "open_file"):
        d.open_file(path)
        return True
    return False


def close_all_windows():
    """Закрыть все окна приложений."""
    d = _desktop()
    if d:
        for w in list(getattr(d, "windows", [])):
            try:
                w.close()
            except RuntimeError:
                pass


def windows():
    """Список всех открытых окон MountOS."""
    d = _desktop()
    return list(getattr(d, "windows", [])) if d else []


# ============================================================
#  Информация о системе
# ============================================================

def version() -> str:
    return "1.0"


def codename() -> str:
    return "Liquid Glass"


def app_list() -> dict:
    """Список установленных приложений: {app_id: name}."""
    d = _desktop()
    if d and hasattr(d, "registry"):
        return {k: v.name for k, v in d.registry.apps.items()}
    return {}


def app_info(app_id: str):
    """Полная информация о приложении или None."""
    d = _desktop()
    if d and hasattr(d, "registry"):
        return d.registry.get(app_id)
    return None


def desktop():
    """Прямой доступ к объекту Desktop (для продвинутых)."""
    return _desktop()


# ============================================================
#  Работа с рабочим столом
# ============================================================

def add_shortcut(app_id: str) -> bool:
    """Создать ярлык приложения на рабочем столе."""
    d = _desktop()
    if d and hasattr(d, "add_app_shortcut"):
        d.add_app_shortcut(app_id)
        return True
    return False


def add_widget(widget_id: str) -> bool:
    """Добавить виджет на рабочий стол.
    widget_id: clock | system | sticky | weather | quick
    """
    d = _desktop()
    if d and hasattr(d, "add_widget"):
        d.add_widget(widget_id)
        return True
    return False


# ============================================================
#  Re-export PySide6 — чтобы разработчику не нужны были лишние импорты
# ============================================================

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                                QPushButton, QLineEdit, QTextEdit,
                                QListWidget, QListWidgetItem, QCheckBox,
                                QSlider, QComboBox, QSpinBox, QProgressBar,
                                QScrollArea, QFrame, QGridLayout, QSplitter,
                                QFileDialog, QMessageBox, QInputDialog)
from PySide6.QtCore import Qt, QTimer, QTime, QDate, Signal, QSize, QPoint
from PySide6.QtGui import QIcon, QPixmap, QColor, QFont, QPainter


# ============================================================
#  Готовые стили-хелперы
# ============================================================

def glass_button(text: str = "") -> QPushButton:
    """Полупрозрачная кнопка."""
    b = QPushButton(text)
    b.setCursor(Qt.PointingHandCursor)
    b.setStyleSheet("""
        QPushButton {
            background: rgba(255,255,255,0.10);
            color: white;
            border: 1px solid rgba(255,255,255,0.16);
            border-radius: 10px;
            padding: 8px 16px;
            font-size: 13px;
        }
        QPushButton:hover { background: rgba(255,255,255,0.22); }
        QPushButton:pressed { background: rgba(110,198,255,0.45); }
    """)
    return b


def accent_button(text: str = "") -> QPushButton:
    """Акцентная кнопка."""
    b = QPushButton(text)
    b.setCursor(Qt.PointingHandCursor)
    b.setStyleSheet("""
        QPushButton {
            background: rgba(110,198,255,0.28);
            color: white;
            border: 1px solid rgba(110,198,255,0.60);
            border-radius: 10px;
            padding: 8px 16px;
            font-size: 13px;
            font-weight: 600;
        }
        QPushButton:hover { background: rgba(110,198,255,0.48); }
    """)
    return b


def danger_button(text: str = "") -> QPushButton:
    """Красная кнопка."""
    b = QPushButton(text)
    b.setCursor(Qt.PointingHandCursor)
    b.setStyleSheet("""
        QPushButton {
            background: rgba(255,107,138,0.18);
            color: #FFA0B4;
            border: 1px solid rgba(255,107,138,0.45);
            border-radius: 10px;
            padding: 8px 16px;
            font-size: 13px;
        }
        QPushButton:hover { background: rgba(255,107,138,0.35); color: white; }
    """)
    return b


def glass_input(placeholder: str = "") -> QLineEdit:
    """Поле ввода в стиле MountOS."""
    e = QLineEdit()
    e.setPlaceholderText(placeholder)
    e.setStyleSheet("""
        QLineEdit {
            background: rgba(255,255,255,0.08);
            color: white;
            border: 1px solid rgba(255,255,255,0.15);
            border-radius: 10px;
            padding: 8px 12px;
            font-size: 13px;
        }
        QLineEdit:focus { border: 1px solid rgba(110,198,255,0.6); }
    """)
    return e


def glass_textedit(placeholder: str = "") -> QTextEdit:
    """Многострочное поле ввода."""
    e = QTextEdit()
    e.setPlaceholderText(placeholder)
    e.setStyleSheet("""
        QTextEdit {
            background: rgba(0,0,0,0.22);
            color: white;
            border: 1px solid rgba(255,255,255,0.10);
            border-radius: 12px;
            padding: 12px;
            font-size: 13px;
        }
        QTextEdit:focus { border: 1px solid rgba(110,198,255,0.5); }
    """)
    return e


def title_label(text: str) -> QLabel:
    l = QLabel(text)
    l.setStyleSheet("color: white; font-size: 18px; font-weight: 600;")
    return l


def text_label(text: str) -> QLabel:
    l = QLabel(text)
    l.setStyleSheet("color: rgba(255,255,255,0.75); font-size: 13px;")
    return l


def hint_label(text: str) -> QLabel:
    l = QLabel(text)
    l.setWordWrap(True)
    l.setStyleSheet("color: rgba(255,255,255,0.45); font-size: 11px;")
    return l