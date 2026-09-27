"""
MountOS — Магазин приложений.

Каталог .py-приложений с установкой по URL:
  • Список приложений с описанием, автором, категорией
  • Установка одним кликом — скачивает .py в system/user_apps/
  • Обновление до последней версии
  • Удаление установленных приложений
  • Поиск, фильтр по категории
  • Локальный кеш каталога в VFS (работает офлайн)
  • Импорт каталога из интернета (JSON)
  • Свой каталог: можно подсунуть свой JSON-файл

Формат каталога (JSON):
    {
      "version": 1,
      "updated": "2026-09-26",
      "apps": [
        {
          "id": "paint",
          "name": "Paint",
          "description": "Простой графический редактор",
          "author": "MountOS Team",
          "version": "1.0",
          "icon": "gallery",
          "category": "Творчество",
          "url": "https://example.com/paint.py",
          "size": 12456,
          "tags": ["графика", "рисование"]
        }
      ]
    }

Установка: apps/appstore.py + перезапуск MountOS.
"""

import json
import os
import time
import urllib.request
import urllib.error
from datetime import datetime

from PySide6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QLabel,
                                QPushButton, QLineEdit, QListWidget,
                                QListWidgetItem, QScrollArea, QFrame,
                                QComboBox, QMessageBox, QDialog,
                                QDialogButtonBox, QTextEdit, QInputDialog,
                                QProgressBar, QSplitter, QSizePolicy)
from PySide6.QtCore import Qt, QTimer, QThread, Signal, QSize
from PySide6.QtGui import QIcon, QColor, QFont, QPainter

from ui.icons import get_icon
from ui.settings_state import state
from ui.context_menu import make_menu

APP_NAME = "Магазин"
APP_ICON = "plus"
APP_VERSION = "1.0"
APP_AUTHOR = "MountOS"


CACHE_PATH = "/Notes/appstore_cache.json"
CUSTOM_CATALOG_PATH = "/Notes/appstore_custom.json"
USER_APPS_DIR = "system/user_apps"

# Демонстрационный каталог — по умолчанию пустой список URL
# Пользователь может загрузить свой
DEFAULT_CATALOG_URL = ""   # пусто — начинаем с локального каталога


# ============================================================
#  Поиск VFS / Desktop
# ============================================================

def _get_vfs(widget):
    p = widget
    while p is not None:
        if hasattr(p, "vfs"):
            return p.vfs
        if hasattr(p, "desktop_ref") and p.desktop_ref is not None:
            return getattr(p.desktop_ref, "vfs", None)
        p = p.parent()
    from PySide6.QtWidgets import QApplication
    for top in QApplication.topLevelWidgets():
        if hasattr(top, "vfs"):
            return top.vfs
        ref = getattr(top, "desktop_ref", None)
        if ref is not None and hasattr(ref, "vfs"):
            return ref.vfs
    return None


def _get_desktop(widget):
    p = widget
    while p is not None:
        if hasattr(p, "notifications") and hasattr(p, "open_app"):
            return p
        if hasattr(p, "desktop_ref") and p.desktop_ref is not None:
            return p.desktop_ref
        p = p.parent()
    from PySide6.QtWidgets import QApplication
    for top in QApplication.topLevelWidgets():
        if hasattr(top, "notifications") and hasattr(top, "open_app"):
            return top
        ref = getattr(top, "desktop_ref", None)
        if ref is not None:
            return ref
    return None


def _get_base_dir(widget):
    d = _get_desktop(widget)
    if d and hasattr(d, "base_dir"):
        return d.base_dir
    from PySide6.QtWidgets import QApplication
    for top in QApplication.topLevelWidgets():
        if hasattr(top, "base_dir"):
            return top.base_dir
    return None


# ============================================================
#  Воркеры
# ============================================================

class CatalogWorker(QThread):
    """Загружает каталог по URL."""
    data_ready = Signal(dict)
    error = Signal(str)

    def __init__(self, url: str):
        super().__init__()
        self.url = url

    def run(self):
        try:
            req = urllib.request.Request(
                self.url,
                headers={"User-Agent": "MountOS/1.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw = resp.read().decode("utf-8")
            data = json.loads(raw)
            if not isinstance(data, dict) or "apps" not in data:
                raise ValueError("Неверный формат каталога")
            self.data_ready.emit(data)
        except Exception as e:
            self.error.emit(str(e))


class InstallWorker(QThread):
    """Скачивает .py-файл приложения."""
    progress = Signal(int, int)     # bytes_done, bytes_total
    finished = Signal(bool, str)    # success, message
    error = Signal(str)

    def __init__(self, url: str, dest_path: str):
        super().__init__()
        self.url = url
        self.dest_path = dest_path

    def run(self):
        try:
            req = urllib.request.Request(
                self.url,
                headers={"User-Agent": "MountOS/1.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                total = int(resp.headers.get("Content-Length", 0))
                chunks = []
                done = 0
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    chunks.append(chunk)
                    done += len(chunk)
                    self.progress.emit(done, total)
                data = b"".join(chunks)

            # Проверяем что это .py-файл
            try:
                text = data.decode("utf-8")
                if "def build" not in text:
                    self.finished.emit(
                        False,
                        "Файл не содержит функцию build() — это не приложение MountOS.")
                    return
            except UnicodeDecodeError:
                self.finished.emit(False, "Файл не является текстом UTF-8.")
                return

            # Сохраняем
            os.makedirs(os.path.dirname(self.dest_path), exist_ok=True)
            with open(self.dest_path, "wb") as f:
                f.write(data)

            self.finished.emit(True, self.dest_path)
        except Exception as e:
            self.error.emit(str(e))


# ============================================================
#  Основное приложение
# ============================================================

def build():
    root = QWidget()
    h = QHBoxLayout(root)
    h.setContentsMargins(0, 0, 0, 0)
    h.setSpacing(0)

    vfs = _get_vfs(root)
    desktop = _get_desktop(root)
    base_dir = _get_base_dir(root)

    st = {
        "catalog": {"apps": []},         # текущий каталог
        "installed": {},                  # app_id -> filepath
        "category": "__all__",
        "search": "",
        "catalog_worker": None,
        "install_worker": None,
        "selected_app": None,
    }

    # ---- Загрузка кеша каталога ----
    if vfs:
        try:
            raw = vfs.read_text(CACHE_PATH, "")
            if raw.strip():
                st["catalog"] = json.loads(raw)
        except Exception:
            pass

    # ---- Сканируем установленные приложения ----
    def scan_installed():
        st["installed"] = {}
        if not base_dir:
            return
        # user_apps
        user_dir = os.path.join(base_dir, USER_APPS_DIR)
        if os.path.isdir(user_dir):
            for f in os.listdir(user_dir):
                if f.endswith(".py") and not f.startswith("_"):
                    app_id = f[:-3]
                    st["installed"][app_id] = os.path.join(user_dir, f)

    scan_installed()

    def save_cache():
        if vfs is None:
            return
        try:
            vfs.mkdir("/Notes")
            vfs.write_text(CACHE_PATH,
                json.dumps(st["catalog"], ensure_ascii=False, indent=2))
        except Exception:
            pass

    # ============================================================
    #  Левая панель — фильтры
    # ============================================================
    side = QWidget()
    side.setFixedWidth(260)
    side.setStyleSheet("""
        background: rgba(255,255,255,0.04);
        border-right: 1px solid rgba(255,255,255,0.08);
    """)
    sl = QVBoxLayout(side)
    sl.setContentsMargins(14, 16, 14, 16)
    sl.setSpacing(10)

    title = QLabel("🛒  Магазин")
    title.setStyleSheet("color: white; font-size: 16px; font-weight: 600; padding: 2px;")
    sl.addWidget(title)

    hint = QLabel("Устанавливай .py-приложения MountOS в один клик")
    hint.setStyleSheet("color: rgba(255,255,255,0.55); font-size: 11px;")
    hint.setWordWrap(True)
    sl.addWidget(hint)

    # URL каталога
    url_lbl = QLabel("URL каталога")
    url_lbl.setStyleSheet("""
        color: rgba(255,255,255,0.45);
        font-size: 10px;
        font-weight: 700;
        letter-spacing: 1.5px;
        padding-top: 6px;
    """)
    sl.addWidget(url_lbl)

    url_input = QLineEdit()
    url_input.setPlaceholderText("https://example.com/catalog.json")
    url_input.setStyleSheet("""
        QLineEdit {
            background: rgba(255,255,255,0.08);
            color: white;
            border: 1px solid rgba(255,255,255,0.15);
            border-radius: 10px;
            padding: 8px 12px;
            font-size: 11px;
        }
        QLineEdit:focus { border: 1px solid rgba(110,198,255,0.6); }
    """)
    sl.addWidget(url_input)

    load_btn = QPushButton("⬇  Загрузить каталог")
    load_btn.setCursor(Qt.PointingHandCursor)
    load_btn.setFixedHeight(36)
    load_btn.setStyleSheet("""
        QPushButton {
            background: rgba(110,198,255,0.22);
            color: white;
            border: 1px solid rgba(110,198,255,0.55);
            border-radius: 10px;
            font-size: 12px;
            font-weight: 600;
        }
        QPushButton:hover { background: rgba(110,198,255,0.42); }
    """)
    sl.addWidget(load_btn)

    import_btn = QPushButton("📁  Импорт из VFS")
    import_btn.setCursor(Qt.PointingHandCursor)
    import_btn.setFixedHeight(34)
    import_btn.setStyleSheet("""
        QPushButton {
            background: rgba(255,255,255,0.06);
            color: white;
            border: 1px solid rgba(255,255,255,0.12);
            border-radius: 10px;
            font-size: 11px;
        }
        QPushButton:hover { background: rgba(255,255,255,0.18); }
    """)
    sl.addWidget(import_btn)

    # Поиск
    search_lbl = QLabel("ПОИСК")
    search_lbl.setStyleSheet(url_lbl.styleSheet())
    sl.addWidget(search_lbl)

    search_input = QLineEdit()
    search_input.setPlaceholderText("Название, автор, тег…")
    search_input.setStyleSheet(url_input.styleSheet())
    sl.addWidget(search_input)

    # Категории
    cat_lbl = QLabel("КАТЕГОРИИ")
    cat_lbl.setStyleSheet(url_lbl.styleSheet())
    sl.addWidget(cat_lbl)

    cat_list = QListWidget()
    cat_list.setStyleSheet("""
        QListWidget {
            background: rgba(0,0,0,0.20);
            color: white;
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 10px;
            padding: 4px;
            font-size: 12px;
            outline: none;
        }
        QListWidget::item { padding: 7px 10px; border-radius: 6px; }
        QListWidget::item:hover { background: rgba(255,255,255,0.08); }
        QListWidget::item:selected { background: rgba(110,198,255,0.30); }
    """)
    sl.addWidget(cat_list, 1)

    # Инфо-строка
    info_lbl = QLabel("Каталог пуст")
    info_lbl.setStyleSheet("""
        color: rgba(255,255,255,0.55);
        font-size: 11px;
        background: rgba(0,0,0,0.20);
        border-radius: 8px;
        padding: 8px 10px;
    """)
    info_lbl.setWordWrap(True)
    sl.addWidget(info_lbl)

    # Кнопка удаления установленных
    refresh_btn = QPushButton("🔄  Обновить список")
    refresh_btn.setCursor(Qt.PointingHandCursor)
    refresh_btn.setFixedHeight(34)
    refresh_btn.setStyleSheet("""
        QPushButton {
            background: rgba(255,255,255,0.06);
            color: white;
            border: 1px solid rgba(255,255,255,0.12);
            border-radius: 10px;
            font-size: 11px;
        }
        QPushButton:hover { background: rgba(255,255,255,0.18); }
    """)
    sl.addWidget(refresh_btn)

    h.addWidget(side)

    # ============================================================
    #  Центр — список приложений
    # ============================================================
    center = QWidget()
    cl = QVBoxLayout(center)
    cl.setContentsMargins(0, 0, 0, 0)
    cl.setSpacing(0)

    # Верхняя панель
    topbar = QWidget()
    topbar.setFixedHeight(52)
    topbar.setStyleSheet("""
        background: rgba(255,255,255,0.04);
        border-bottom: 1px solid rgba(255,255,255,0.08);
    """)
    tbl = QHBoxLayout(topbar)
    tbl.setContentsMargins(14, 8, 14, 8)
    tbl.setSpacing(8)

    page_title = QLabel("Каталог приложений")
    page_title.setStyleSheet("color: white; font-size: 14px; font-weight: 600;")
    tbl.addWidget(page_title)
    tbl.addStretch(1)

    # Счётчик
    count_lbl = QLabel("0 приложений")
    count_lbl.setStyleSheet("color: rgba(255,255,255,0.55); font-size: 12px;")
    tbl.addWidget(count_lbl)

    cl.addWidget(topbar)

    # Список приложений
    apps_scroll = QScrollArea()
    apps_scroll.setWidgetResizable(True)
    apps_scroll.setFrameShape(QFrame.NoFrame)
    apps_scroll.setStyleSheet("""
        QScrollArea { background: transparent; border: none; }
        QScrollBar:vertical {
            background: transparent; width: 8px; margin: 4px;
        }
        QScrollBar::handle:vertical {
            background: rgba(255,255,255,0.20);
            border-radius: 4px;
            min-height: 40px;
        }
        QScrollBar::handle:vertical:hover { background: rgba(255,255,255,0.35); }
        QScrollBar::add-line, QScrollBar::sub-line { height: 0; }
    """)

    apps_holder = QWidget()
    apps_holder.setStyleSheet("background: transparent;")
    apps_list_layout = QVBoxLayout(apps_holder)
    apps_list_layout.setContentsMargins(20, 16, 20, 16)
    apps_list_layout.setSpacing(10)
    apps_list_layout.addStretch(1)
    apps_scroll.setWidget(apps_holder)
    cl.addWidget(apps_scroll, 1)

    # Пустое состояние
    empty_lbl = QLabel(
        "🛒  Каталог пуст\n\n"
        "Введи URL каталога слева или импортируй JSON из VFS.\n"
        "Формат каталога — обычный JSON со списком приложений."
    )
    empty_lbl.setAlignment(Qt.AlignCenter)
    empty_lbl.setStyleSheet("""
        color: rgba(255,255,255,0.45);
        font-size: 13px;
        padding: 80px 20px;
        background: transparent;
    """)
    empty_lbl.setWordWrap(True)
    apps_list_layout.insertWidget(0, empty_lbl)

    h.addWidget(center, 1)

    # ============================================================
    #  Карточка приложения
    # ============================================================

    def make_app_card(app: dict) -> QWidget:
        """Карточка одного приложения."""
        app_id = app.get("id", "?")
        name = app.get("name", "Без имени")
        desc = app.get("description", "")
        author = app.get("author", "неизвестно")
        version = app.get("version", "—")
        icon_name = app.get("icon", "star")
        category = app.get("category", "Разное")
        url = app.get("url", "")
        tags = app.get("tags", [])

        installed = app_id in st["installed"]

        card = QWidget()
        card.setStyleSheet("""
            QWidget {
                background: rgba(255,255,255,0.05);
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 14px;
            }
            QWidget:hover {
                background: rgba(255,255,255,0.08);
                border: 1px solid rgba(255,255,255,0.14);
            }
        """)
        card.setMinimumHeight(120)

        lay = QHBoxLayout(card)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(16)

        # Иконка
        icon_lbl = QLabel()
        icon_lbl.setFixedSize(64, 64)
        icon_lbl.setAlignment(Qt.AlignCenter)
        pm = get_icon(icon_name, 44, state().get("accent", "#6EC6FF"))
        icon_lbl.setPixmap(pm)
        icon_lbl.setStyleSheet("""
            background: rgba(110,198,255,0.10);
            border: 1px solid rgba(110,198,255,0.35);
            border-radius: 16px;
        """)
        lay.addWidget(icon_lbl)

        # Инфо
        info_col = QVBoxLayout()
        info_col.setContentsMargins(0, 0, 0, 0)
        info_col.setSpacing(4)

        # Имя + версия
        name_row = QHBoxLayout()
        name_row.setSpacing(8)
        name_lbl = QLabel(name)
        name_lbl.setStyleSheet("""
            color: white;
            font-size: 16px;
            font-weight: 600;
            background: transparent;
            border: none;
        """)
        name_row.addWidget(name_lbl)

        ver_lbl = QLabel(f"v{version}")
        ver_lbl.setStyleSheet("""
            color: rgba(255,255,255,0.55);
            font-size: 11px;
            background: transparent;
            border: none;
        """)
        name_row.addWidget(ver_lbl)
        name_row.addStretch(1)

        if installed:
            badge = QLabel("✓  Установлено")
            badge.setStyleSheet("""
                background: rgba(110,231,183,0.20);
                color: #6EE7B7;
                border: 1px solid rgba(110,231,183,0.50);
                border-radius: 8px;
                padding: 3px 10px;
                font-size: 10px;
                font-weight: 600;
            """)
            name_row.addWidget(badge)

        info_col.addLayout(name_row)

        # Автор + категория
        meta_lbl = QLabel(f"👤  {author}    ·    📁  {category}")
        meta_lbl.setStyleSheet("""
            color: rgba(255,255,255,0.55);
            font-size: 11px;
            background: transparent;
            border: none;
        """)
        info_col.addWidget(meta_lbl)

        # Описание
        desc_lbl = QLabel(desc or "Без описания")
        desc_lbl.setStyleSheet("""
            color: rgba(255,255,255,0.75);
            font-size: 12px;
            background: transparent;
            border: none;
        """)
        desc_lbl.setWordWrap(True)
        info_col.addWidget(desc_lbl)

        # Теги
        if tags:
            tags_lbl = QLabel("  ".join(f"#{t}" for t in tags))
            tags_lbl.setStyleSheet("""
                color: rgba(110,198,255,0.75);
                font-size: 10px;
                background: transparent;
                border: none;
            """)
            info_col.addWidget(tags_lbl)

        info_col.addStretch(1)
        lay.addLayout(info_col, 1)

        # Кнопки
        btn_col = QVBoxLayout()
        btn_col.setContentsMargins(0, 0, 0, 0)
        btn_col.setSpacing(6)

        install_btn = QPushButton()
        install_btn.setFixedSize(120, 36)
        install_btn.setCursor(Qt.PointingHandCursor)

        if installed:
            install_btn.setText("🗑  Удалить")
            install_btn.setStyleSheet("""
                QPushButton {
                    background: rgba(255,107,138,0.15);
                    color: #FFA0B4;
                    border: 1px solid rgba(255,107,138,0.45);
                    border-radius: 10px;
                    font-size: 12px;
                    font-weight: 600;
                }
                QPushButton:hover {
                    background: rgba(255,107,138,0.35);
                    color: white;
                }
            """)
            install_btn.clicked.connect(lambda: uninstall_app(app_id))
        else:
            install_btn.setText("⬇  Установить")
            install_btn.setStyleSheet("""
                QPushButton {
                    background: rgba(110,198,255,0.25);
                    color: white;
                    border: 1px solid rgba(110,198,255,0.60);
                    border-radius: 10px;
                    font-size: 12px;
                    font-weight: 600;
                }
                QPushButton:hover { background: rgba(110,198,255,0.45); }
            """)
            install_btn.clicked.connect(lambda: install_app(app))

        btn_col.addWidget(install_btn)

        # Кнопка "Открыть" (если установлено)
        if installed and desktop:
            open_btn = QPushButton("▶  Открыть")
            open_btn.setFixedSize(120, 32)
            open_btn.setCursor(Qt.PointingHandCursor)
            open_btn.setStyleSheet("""
                QPushButton {
                    background: rgba(110,231,183,0.18);
                    color: #6EE7B7;
                    border: 1px solid rgba(110,231,183,0.45);
                    border-radius: 10px;
                    font-size: 12px;
                }
                QPushButton:hover {
                    background: rgba(110,231,183,0.35);
                    color: white;
                }
            """)
            open_btn.clicked.connect(lambda: open_app(app_id))
            btn_col.addWidget(open_btn)

        btn_col.addStretch(1)
        lay.addLayout(btn_col)

        # Контекстное меню
        card.setContextMenuPolicy(Qt.CustomContextMenu)

        def show_menu(pos, app=app):
            menu = make_menu(card)

            a_info = menu.addAction("ℹ  Информация")
            a_info.triggered.connect(lambda: show_info(app))

            if app.get("url"):
                a_copy = menu.addAction("📋  Копировать URL")
                from PySide6.QtWidgets import QApplication
                a_copy.triggered.connect(
                    lambda: QApplication.clipboard().setText(app["url"]))

            menu.exec(card.mapToGlobal(pos))

        card.customContextMenuRequested.connect(show_menu)

        # Двойной клик — информация
        card.mouseDoubleClickEvent = lambda e, a=app: show_info(a)

        return card

    # ============================================================
    #  Логика
    # ============================================================

    def refresh_categories():
        """Обновляет список категорий."""
        # Собираем категории
        cats = set()
        for app in st["catalog"].get("apps", []):
            cats.add(app.get("category", "Разное"))

        cat_list.clear()
        all_item = QListWidgetItem(f"🌐  Все категории  ({len(st['catalog'].get('apps', []))})")
        all_item.setData(Qt.UserRole, "__all__")
        cat_list.addItem(all_item)

        for c in sorted(cats):
            count = sum(1 for a in st["catalog"].get("apps", [])
                        if a.get("category", "Разное") == c)
            item = QListWidgetItem(f"📁  {c}  ({count})")
            item.setData(Qt.UserRole, c)
            cat_list.addItem(item)

        cat_list.setCurrentRow(0)

    def refresh_apps():
        """Перерисовывает список приложений."""
        # Очищаем
        for i in reversed(range(apps_list_layout.count())):
            it = apps_list_layout.itemAt(i)
            w = it.widget() if it else None
            if w and w is not empty_lbl:
                w.setParent(None)
        empty_lbl.setParent(None)

        apps = st["catalog"].get("apps", [])
        query = st["search"].lower()
        cat = st["category"]

        # Фильтр
        filtered = []
        for app in apps:
            if cat != "__all__" and app.get("category", "Разное") != cat:
                continue
            if query:
                searchable = (
                    app.get("name", "") + " " +
                    app.get("description", "") + " " +
                    app.get("author", "") + " " +
                    " ".join(app.get("tags", []))
                ).lower()
                if query not in searchable:
                    continue
            filtered.append(app)

        if not filtered:
            if not apps:
                empty_lbl.setText(
                    "🛒  Каталог пуст\n\n"
                    "Введи URL каталога слева или импортируй JSON из VFS.\n"
                    "Формат каталога — JSON со списком приложений."
                )
            else:
                empty_lbl.setText("🔍  Ничего не найдено")
            empty_lbl.show()
            apps_list_layout.insertWidget(0, empty_lbl)
        else:
            empty_lbl.hide()
            for app in filtered:
                card = make_app_card(app)
                apps_list_layout.insertWidget(apps_list_layout.count() - 1, card)

        # Обновляем счётчик
        count_lbl.setText(f"{len(filtered)} из {len(apps)}")
        # Инфо
        if apps:
            updated = st["catalog"].get("updated", "—")
            info_lbl.setText(
                f"Всего: {len(apps)}\n"
                f"Установлено: {len(st['installed'])}\n"
                f"Обновлено: {updated}"
            )

    def refresh_all():
        refresh_categories()
        refresh_apps()

    # ============================================================
    #  Установка
    # ============================================================

    def install_app(app: dict):
        if not base_dir:
            QMessageBox.warning(root, "Ошибка", "Не могу найти папку MountOS.")
            return
        url = app.get("url", "")
        if not url:
            QMessageBox.warning(root, "Ошибка", "У приложения нет URL.")
            return

        app_id = app.get("id", "app")
        # Проверка имени
        safe_id = "".join(c for c in app_id if c.isalnum() or c in "_-")
        if not safe_id:
            safe_id = "app_" + str(int(time.time()))

        dest = os.path.join(base_dir, USER_APPS_DIR, f"{safe_id}.py")

        if os.path.exists(dest):
            ans = QMessageBox.question(
                root, "Уже существует",
                f"Приложение {safe_id} уже установлено.\nПерезаписать?",
                QMessageBox.Yes | QMessageBox.No)
            if ans != QMessageBox.Yes:
                return

        # Показываем прогресс
        progress_dlg = QDialog(root)
        progress_dlg.setWindowTitle(f"Установка {app.get('name', '')}")
        progress_dlg.setFixedSize(400, 120)
        progress_dlg.setStyleSheet("QDialog { background: #1A1F35; }")
        pl = QVBoxLayout(progress_dlg)
        pl.setContentsMargins(20, 20, 20, 20)
        pl.setSpacing(12)

        lbl = QLabel(f"Скачиваю {app.get('name', '')}…")
        lbl.setStyleSheet("color: white; font-size: 13px;")
        pl.addWidget(lbl)

        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(0)
        bar.setTextVisible(False)
        bar.setFixedHeight(8)
        bar.setStyleSheet("""
            QProgressBar {
                background: rgba(255,255,255,0.10);
                border: none;
                border-radius: 4px;
            }
            QProgressBar::chunk {
                background: #6EC6FF;
                border-radius: 4px;
            }
        """)
        pl.addWidget(bar)

        progress_dlg.show()

        worker = InstallWorker(url, dest)
        st["install_worker"] = worker

        def on_progress(done, total):
            if total > 0:
                bar.setValue(int(done / total * 100))

        def on_finished(success, msg):
            progress_dlg.close()
            if success:
                if desktop and hasattr(desktop, "notifications"):
                    desktop.notifications.push(
                        "Приложение установлено",
                        f"{app.get('name', safe_id)}")
                QMessageBox.information(root, "Готово",
                    f"Приложение «{app.get('name', '')}» установлено.\n\n"
                    f"Файл: {msg}\n\n"
                    f"Оно появится в доке MountOS.")
                # Обновляем реестр MountOS
                try:
                    from PySide6.QtWidgets import QApplication
                    for top in QApplication.topLevelWidgets():
                        if hasattr(top, "registry") and hasattr(top.registry, "apps"):
                            top.registry.install(msg)
                            if hasattr(top, "dock"):
                                top.dock.populate(top.registry.apps)
                            break
                        ref = getattr(top, "desktop_ref", None)
                        if ref is not None and hasattr(ref, "registry"):
                            ref.registry.install(msg)
                            if hasattr(ref, "dock"):
                                ref.dock.populate(ref.registry.apps)
                            break
                except Exception as e:
                    print(f"[AppStore] registry install: {e}")

                scan_installed()
                refresh_apps()
            else:
                QMessageBox.warning(root, "Ошибка установки", msg)

        def on_error(err):
            progress_dlg.close()
            QMessageBox.warning(root, "Ошибка", err)

        worker.progress.connect(on_progress)
        worker.finished.connect(on_finished)
        worker.error.connect(on_error)
        worker.start()

    def uninstall_app(app_id: str):
        if app_id not in st["installed"]:
            QMessageBox.information(root, "Не установлено",
                f"Приложение {app_id} не установлено.")
            return
        path = st["installed"][app_id]
        ans = QMessageBox.question(
            root, "Удалить приложение",
            f"Удалить {app_id}?\n\nФайл {path}\nбудет стёрт с диска.",
            QMessageBox.Yes | QMessageBox.No)
        if ans != QMessageBox.Yes:
            return
        try:
            os.remove(path)
            if desktop and hasattr(desktop, "notifications"):
                desktop.notifications.push("Приложение удалено", app_id)

            # Обновляем реестр
            try:
                from PySide6.QtWidgets import QApplication
                for top in QApplication.topLevelWidgets():
                    if hasattr(top, "registry") and hasattr(top.registry, "apps"):
                        top.registry.remove(app_id)
                        if hasattr(top, "dock"):
                            top.dock.populate(top.registry.apps)
                        break
                    ref = getattr(top, "desktop_ref", None)
                    if ref is not None and hasattr(ref, "registry"):
                        ref.registry.remove(app_id)
                        if hasattr(ref, "dock"):
                            ref.dock.populate(ref.registry.apps)
                        break
            except Exception:
                pass

            scan_installed()
            refresh_apps()
        except Exception as e:
            QMessageBox.warning(root, "Ошибка удаления", str(e))

    def open_app(app_id: str):
        if desktop and hasattr(desktop, "open_app"):
            desktop.open_app(app_id)

    # ============================================================
    #  Информация о приложении
    # ============================================================

    def show_info(app: dict):
        dlg = QDialog(root)
        dlg.setWindowTitle(app.get("name", "Приложение"))
        dlg.resize(500, 420)
        dlg.setStyleSheet("QDialog { background: #1A1F35; }")

        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(24, 24, 24, 24)
        lay.setSpacing(14)

        header = QHBoxLayout()
        header.setSpacing(16)

        ic = QLabel()
        ic.setFixedSize(72, 72)
        ic.setAlignment(Qt.AlignCenter)
        ic.setPixmap(get_icon(app.get("icon", "star"), 52,
                                state().get("accent", "#6EC6FF")))
        ic.setStyleSheet("""
            background: rgba(110,198,255,0.10);
            border: 1px solid rgba(110,198,255,0.35);
            border-radius: 18px;
        """)
        header.addWidget(ic)

        text_col = QVBoxLayout()
        text_col.setSpacing(4)

        name = QLabel(app.get("name", "—"))
        name.setStyleSheet("""
            color: white;
            font-size: 22px;
            font-weight: 600;
            background: transparent;
        """)
        text_col.addWidget(name)

        meta = QLabel(f"Автор: {app.get('author', '—')}  ·  "
                       f"Версия: {app.get('version', '—')}")
        meta.setStyleSheet("color: rgba(255,255,255,0.65); font-size: 12px;")
        text_col.addWidget(meta)

        cat = QLabel(f"📁  {app.get('category', 'Разное')}")
        cat.setStyleSheet("color: rgba(110,198,255,0.85); font-size: 12px;")
        text_col.addWidget(cat)

        text_col.addStretch(1)
        header.addLayout(text_col, 1)

        lay.addLayout(header)

        # Описание
        desc = QTextEdit()
        desc.setPlainText(app.get("description", "Без описания"))
        desc.setReadOnly(True)
        desc.setStyleSheet("""
            QTextEdit {
                background: rgba(0,0,0,0.22);
                color: white;
                border: 1px solid rgba(255,255,255,0.10);
                border-radius: 10px;
                padding: 12px;
                font-size: 13px;
            }
        """)
        lay.addWidget(desc, 1)

        # URL
        if app.get("url"):
            url_lbl = QLabel(f"URL: {app['url']}")
            url_lbl.setStyleSheet("""
                color: rgba(255,255,255,0.55);
                font-size: 11px;
                font-family: Consolas, monospace;
                background: rgba(0,0,0,0.20);
                border-radius: 6px;
                padding: 6px 10px;
            """)
            url_lbl.setWordWrap(True)
            url_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
            lay.addWidget(url_lbl)

        # Теги
        if app.get("tags"):
            tags_lbl = QLabel("  ".join(f"#{t}" for t in app["tags"]))
            tags_lbl.setStyleSheet("color: rgba(110,198,255,0.75); font-size: 11px;")
            lay.addWidget(tags_lbl)

        btns = QDialogButtonBox(QDialogButtonBox.Close)
        btns.rejected.connect(dlg.reject)
        btns.setStyleSheet("""
            QPushButton {
                background: rgba(110,198,255,0.20);
                color: white;
                border: 1px solid rgba(110,198,255,0.50);
                border-radius: 8px;
                padding: 8px 20px;
                font-size: 12px;
                min-width: 100px;
            }
            QPushButton:hover { background: rgba(110,198,255,0.40); }
        """)
        lay.addWidget(btns)

        dlg.exec()

    # ============================================================
    #  Загрузка каталога
    # ============================================================

    def load_from_url():
        url = url_input.text().strip()
        if not url:
            QMessageBox.information(root, "URL",
                "Введи URL каталога в поле слева.")
            return
        load_btn.setEnabled(False)
        load_btn.setText("⏳  Загрузка…")

        worker = CatalogWorker(url)
        st["catalog_worker"] = worker

        def on_data(data):
            load_btn.setEnabled(True)
            load_btn.setText("⬇  Загрузить каталог")
            st["catalog"] = data
            save_cache()
            refresh_all()
            if desktop and hasattr(desktop, "notifications"):
                desktop.notifications.push("Каталог обновлён",
                    f"{len(data.get('apps', []))} приложений")

        def on_error(err):
            load_btn.setEnabled(True)
            load_btn.setText("⬇  Загрузить каталог")
            QMessageBox.warning(root, "Ошибка загрузки", err)

        worker.data_ready.connect(on_data)
        worker.error.connect(on_error)
        worker.start()

    load_btn.clicked.connect(load_from_url)
    url_input.returnPressed.connect(load_from_url)

    def import_from_vfs():
        """Импорт каталога из VFS-файла."""
        if vfs is None:
            return
        # Список .json в VFS
        files = []
        def walk(p, depth=0):
            if depth > 5:
                return
            try:
                items = vfs.listdir(p)
            except Exception:
                return
            for it in items:
                if it["is_dir"]:
                    walk(it["path"], depth + 1)
                elif it["name"].lower().endswith(".json"):
                    files.append(it["path"])
        walk("/")

        if not files:
            QMessageBox.information(root, "Импорт",
                "В VFS нет .json файлов.")
            return

        path, ok = QInputDialog.getItem(
            root, "Импорт каталога", "Файл каталога:",
            files, 0, False)
        if not ok:
            return

        try:
            raw = vfs.read_text(path, "")
            data = json.loads(raw)
            if not isinstance(data, dict) or "apps" not in data:
                raise ValueError("Неверный формат: нужен объект с ключом 'apps'")
            st["catalog"] = data
            save_cache()
            refresh_all()
            if desktop and hasattr(desktop, "notifications"):
                desktop.notifications.push("Каталог импортирован",
                    f"{len(data.get('apps', []))} приложений")
        except Exception as e:
            QMessageBox.warning(root, "Ошибка", str(e))

    import_btn.clicked.connect(import_from_vfs)

    def on_search_changed(text):
        st["search"] = text
        refresh_apps()

    search_input.textChanged.connect(on_search_changed)

    def on_category_click(item):
        cat = item.data(Qt.UserRole)
        if cat:
            st["category"] = cat
            refresh_apps()

    cat_list.itemClicked.connect(on_category_click)

    def on_refresh():
        scan_installed()
        refresh_apps()

    refresh_btn.clicked.connect(on_refresh)

    # ============================================================
    #  Стартовая инициализация
    # ============================================================

    # Если каталог пуст — создаём демонстрационный
    if not st["catalog"].get("apps"):
        st["catalog"] = {
            "version": 1,
            "updated": datetime.now().strftime("%Y-%m-%d"),
            "apps": [],
        }
        save_cache()

    refresh_all()

    return root