"""
MountOS — Читалка книг.

Открывает текстовые файлы из VFS:
  • .txt, .md, .log, .fb2, .csv
  • Автоматическая разбивка на «страницы» по высоте окна
  • Настройка шрифта: размер, семейство, межстрочный интервал
  • 4 темы чтения: Тёмная, Сепия, Светлая, Ночная
  • Прогресс сохраняется по каждой книге
  • Закладки — можно отметить место и вернуться
  • Поиск по тексту
  • Режим «плавной прокрутки»
  • Горячие клавиши: ←/→ страницы, Ctrl+F поиск, Ctrl+B закладка

Установка: apps/reader.py + перезапуск MountOS.
"""

import json
import os
import re
import time
from html import unescape

from PySide6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QLabel,
                                QPushButton, QLineEdit, QListWidget,
                                QListWidgetItem, QSlider, QComboBox,
                                QFontComboBox, QScrollArea, QFrame,
                                QMessageBox, QInputDialog, QTextEdit,
                                QSizePolicy, QStackedWidget)
from PySide6.QtCore import Qt, QTimer, QSize, QPoint
from PySide6.QtGui import (QFont, QIcon, QTextCursor, QColor, QPainter,
                            QPixmap, QTextCharFormat, QKeySequence, QShortcut)

from ui.icons import get_icon
from ui.settings_state import state
from ui.context_menu import make_menu

APP_NAME = "Читалка"
APP_ICON = "editor"
APP_VERSION = "1.0"
APP_AUTHOR = "MountOS"


PROGRESS_PATH = "/Notes/reader_progress.json"
BOOKMARKS_PATH = "/Notes/reader_bookmarks.json"


# ============================================================
#  Темы чтения
# ============================================================

THEMES = {
    "dark": {
        "name": "Тёмная",
        "bg": "#141A28",
        "fg": "#E0E6F0",
        "border": "#2A3149",
        "accent": "#6EC6FF",
    },
    "sepia": {
        "name": "Сепия",
        "bg": "#F4ECD8",
        "fg": "#3E2C1E",
        "border": "#D9C9A8",
        "accent": "#8B5A2B",
    },
    "light": {
        "name": "Светлая",
        "bg": "#FFFFFF",
        "fg": "#1A1F35",
        "border": "#DCDCE4",
        "accent": "#0066CC",
    },
    "night": {
        "name": "Ночная",
        "bg": "#0A0E14",
        "fg": "#A8B8C8",
        "border": "#1A2030",
        "accent": "#FF8866",
    },
}


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


# ============================================================
#  Парсеры форматов
# ============================================================

def _strip_html(text: str) -> str:
    """Убирает HTML-теги и декодирует сущности."""
    text = re.sub(r"<[^>]+>", "", text)
    text = unescape(text)
    return text


def load_book_text(vfs, path: str) -> str:
    """Загружает текст книги из VFS с учётом формата."""
    if vfs is None or not vfs.exists(path):
        return ""

    try:
        raw = vfs.read_bytes(path)
        # Пробуем кодировки
        text = None
        for enc in ("utf-8", "utf-8-sig", "cp1251", "latin-1"):
            try:
                text = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        if text is None:
            text = raw.decode("utf-8", errors="replace")

        name_lower = path.lower()

        # FB2 — это XML с тегами
        if name_lower.endswith(".fb2"):
            # Убираем XML-декларацию, теги
            text = re.sub(r"<\?xml[^>]*\?>", "", text)
            text = re.sub(r"<binary[^>]*>.*?</binary>", "", text, flags=re.DOTALL)
            # Заменяем <p> на абзацы
            text = re.sub(r"<p[^>]*>", "\n\n", text)
            text = re.sub(r"<title>", "\n\n═══ ", text)
            text = re.sub(r"</title>", " ═══\n\n", text)
            text = _strip_html(text)
            text = re.sub(r"\n{3,}", "\n\n", text)

        # Markdown — мягкая очистка
        elif name_lower.endswith(".md"):
            # Убираем маркеры заголовков, оставляем текст
            lines = text.split("\n")
            cleaned = []
            for line in lines:
                # Заголовки
                m = re.match(r"^(#{1,6})\s+(.+)$", line)
                if m:
                    level = len(m.group(1))
                    title = m.group(2)
                    if level == 1:
                        cleaned.append("")
                        cleaned.append("═" * min(60, len(title) + 10))
                        cleaned.append(f"  {title.upper()}")
                        cleaned.append("═" * min(60, len(title) + 10))
                        cleaned.append("")
                    elif level == 2:
                        cleaned.append("")
                        cleaned.append(title)
                        cleaned.append("─" * len(title))
                    else:
                        cleaned.append(f"\n{title}\n")
                    continue
                # Жирный/курсив
                line = re.sub(r"\*\*(.+?)\*\*", r"\1", line)
                line = re.sub(r"\*(.+?)\*", r"\1", line)
                line = re.sub(r"__(.+?)__", r"\1", line)
                line = re.sub(r"_(.+?)_", r"\1", line)
                # Код
                line = re.sub(r"`(.+?)`", r"\1", line)
                # Ссылки [text](url) → text
                line = re.sub(r"\[(.+?)\]\(.+?\)", r"\1", line)
                # Списки
                line = re.sub(r"^\s*[-*+]\s+", "  • ", line)
                line = re.sub(r"^\s*\d+\.\s+", "     ", line)
                cleaned.append(line)
            text = "\n".join(cleaned)

        # CSV — заменяем запятые на табы
        elif name_lower.endswith(".csv"):
            lines = text.split("\n")
            for i, line in enumerate(lines):
                if ";" in line and "," not in line:
                    lines[i] = line.replace(";", "  |  ")
                else:
                    lines[i] = line.replace(",", "  |  ")
            text = "\n".join(lines)

        # Убираем \r
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        return text

    except Exception as e:
        print(f"[Reader] load error: {e}")
        return ""


# ============================================================
#  Хранилище прогресса и закладок
# ============================================================

class ReaderStore:
    def __init__(self, vfs):
        self.vfs = vfs
        self.progress = self._load(PROGRESS_PATH, {})
        self.bookmarks = self._load(BOOKMARKS_PATH, {})

    def _load(self, path, default):
        if self.vfs is None:
            return default
        try:
            raw = self.vfs.read_text(path, "")
            if not raw.strip():
                return default
            data = json.loads(raw)
            return data if isinstance(data, dict) else default
        except Exception:
            return default

    def _save(self, path, data):
        if self.vfs is None:
            return
        try:
            self.vfs.mkdir("/Notes")
            self.vfs.write_text(path, json.dumps(data, ensure_ascii=False, indent=2))
        except Exception as e:
            print(f"[Reader] save: {e}")

    def get_progress(self, book_path: str) -> dict:
        return self.progress.get(book_path, {"scroll": 0, "chapter": 0})

    def set_progress(self, book_path: str, scroll: int, chapter: int = 0):
        self.progress[book_path] = {
            "scroll": scroll,
            "chapter": chapter,
            "updated": time.time(),
        }
        self._save(PROGRESS_PATH, self.progress)

    def get_bookmarks(self, book_path: str) -> list:
        return self.bookmarks.get(book_path, [])

    def add_bookmark(self, book_path: str, name: str, position: int):
        lst = self.bookmarks.setdefault(book_path, [])
        lst.append({
            "name": name,
            "position": position,
            "added": time.time(),
        })
        self._save(BOOKMARKS_PATH, self.bookmarks)

    def remove_bookmark(self, book_path: str, index: int):
        lst = self.bookmarks.get(book_path, [])
        if 0 <= index < len(lst):
            lst.pop(index)
            self._save(BOOKMARKS_PATH, self.bookmarks)


# ============================================================
#  Виджет чтения
# ============================================================

class ReaderView(QTextEdit):
    """Текстовое поле с настройками чтения."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setLineWrapMode(QTextEdit.WidgetWidth)
        self.setFrameShape(QFrame.NoFrame)
        self.setTextInteractionFlags(Qt.TextSelectableByMouse |
                                       Qt.TextSelectableByKeyboard)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

    def apply_theme(self, theme_data: dict):
        self.setStyleSheet(f"""
            QTextEdit {{
                background: {theme_data['bg']};
                color: {theme_data['fg']};
                border: none;
                padding: 40px 60px;
                selection-background-color: {theme_data['accent']};
            }}
            QScrollBar:vertical {{
                background: transparent;
                width: 10px;
                margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background: {theme_data['border']};
                border-radius: 5px;
                min-height: 40px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {theme_data['accent']};
            }}
            QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
        """)

    def apply_font(self, family: str, size: int, line_spacing: float = 1.5):
        font = QFont(family, size)
        self.setFont(font)
        # Межстрочный интервал
        cursor = self.textCursor()
        cursor.select(QTextCursor.Document)
        fmt = QTextCharFormat()
        fmt.setFont(font)
        # Применяем через CSS-like line-height
        self.document().setDefaultStyleSheet(
            f"body {{ line-height: {line_spacing}; }}")
        cursor.mergeCharFormat(fmt)


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
    store = ReaderStore(vfs)

    st = {
        "book_path": None,
        "book_title": "",
        "book_text": "",
        "theme": "dark",
        "font_family": "Georgia",
        "font_size": 16,
        "line_spacing": 1.6,
        "search_results": [],
        "search_index": 0,
        "last_search": "",
    }

    # ============================================================
    #  Левая панель — библиотека
    # ============================================================
    side = QWidget()
    side.setFixedWidth(300)
    side.setStyleSheet("""
        background: rgba(255,255,255,0.04);
        border-right: 1px solid rgba(255,255,255,0.08);
    """)
    sl = QVBoxLayout(side)
    sl.setContentsMargins(14, 16, 14, 16)
    sl.setSpacing(10)

    title = QLabel("📚  Читалка")
    title.setStyleSheet("color: white; font-size: 16px; font-weight: 600; padding: 2px;")
    sl.addWidget(title)

    # Поиск книг
    search_books = QLineEdit()
    search_books.setPlaceholderText("Поиск книг…")
    search_books.setStyleSheet("""
        QLineEdit {
            background: rgba(255,255,255,0.08);
            color: white;
            border: 1px solid rgba(255,255,255,0.15);
            border-radius: 10px;
            padding: 8px 12px;
            font-size: 12px;
        }
        QLineEdit:focus { border: 1px solid rgba(110,198,255,0.6); }
    """)
    sl.addWidget(search_books)

    # Список книг
    book_list = QListWidget()
    book_list.setStyleSheet("""
        QListWidget {
            background: rgba(0,0,0,0.20);
            color: white;
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 10px;
            padding: 4px;
            font-size: 12px;
            outline: none;
        }
        QListWidget::item { padding: 8px 10px; border-radius: 6px; }
        QListWidget::item:hover { background: rgba(255,255,255,0.08); }
        QListWidget::item:selected { background: rgba(110,198,255,0.30); }
    """)
    sl.addWidget(book_list, 1)

    # Закладки
    bm_lbl = QLabel("ЗАКЛАДКИ")
    bm_lbl.setStyleSheet("""
        color: rgba(255,255,255,0.45);
        font-size: 10px;
        font-weight: 700;
        letter-spacing: 1.5px;
        padding-top: 6px;
    """)
    sl.addWidget(bm_lbl)

    bookmarks_list = QListWidget()
    bookmarks_list.setStyleSheet(book_list.styleSheet())
    bookmarks_list.setFixedHeight(140)
    sl.addWidget(bookmarks_list)

    h.addWidget(side)

    # ============================================================
    #  Центральная область — текст
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
    tbl.setContentsMargins(12, 8, 12, 8)
    tbl.setSpacing(8)

    book_title_lbl = QLabel("Книга не открыта")
    book_title_lbl.setStyleSheet("""
        color: rgba(255,255,255,0.85);
        font-size: 13px;
        font-weight: 600;
    """)
    tbl.addWidget(book_title_lbl)
    tbl.addStretch(1)

    # Поиск по тексту
    search_input = QLineEdit()
    search_input.setPlaceholderText("🔍 Поиск по тексту…")
    search_input.setFixedWidth(240)
    search_input.setStyleSheet("""
        QLineEdit {
            background: rgba(255,255,255,0.08);
            color: white;
            border: 1px solid rgba(255,255,255,0.15);
            border-radius: 10px;
            padding: 6px 12px;
            font-size: 12px;
        }
        QLineEdit:focus { border: 1px solid rgba(110,198,255,0.6); }
    """)
    tbl.addWidget(search_input)

    search_prev = QPushButton("◀")
    search_prev.setFixedSize(28, 28)
    search_prev.setToolTip("Предыдущее совпадение")
    search_prev.setStyleSheet("""
        QPushButton {
            background: rgba(255,255,255,0.08);
            color: white;
            border: 1px solid rgba(255,255,255,0.12);
            border-radius: 6px;
            font-size: 11px;
        }
        QPushButton:hover { background: rgba(255,255,255,0.20); }
    """)
    tbl.addWidget(search_prev)

    search_next = QPushButton("▶")
    search_next.setFixedSize(28, 28)
    search_next.setToolTip("Следующее совпадение")
    search_next.setStyleSheet(search_prev.styleSheet())
    tbl.addWidget(search_next)

    tbl.addSpacing(10)

    # Закладка
    add_bm_btn = QPushButton("🔖")
    add_bm_btn.setFixedSize(32, 32)
    add_bm_btn.setToolTip("Добавить закладку (Ctrl+B)")
    add_bm_btn.setStyleSheet("""
        QPushButton {
            background: rgba(255,184,108,0.18);
            color: #FFB86C;
            border: 1px solid rgba(255,184,108,0.45);
            border-radius: 8px;
            font-size: 14px;
        }
        QPushButton:hover { background: rgba(255,184,108,0.35); }
    """)
    tbl.addWidget(add_bm_btn)

    cl.addWidget(topbar)

    # Прогресс-бар
    progress_bar = QWidget()
    progress_bar.setFixedHeight(3)
    progress_bar.setStyleSheet("background: rgba(255,255,255,0.06);")
    progress_inner = QWidget(progress_bar)
    progress_inner.setStyleSheet("background: #6EC6FF;")
    progress_inner.setGeometry(0, 0, 0, 3)
    cl.addWidget(progress_bar)

    # Текст
    reader = ReaderView()
    reader.apply_theme(THEMES["dark"])
    reader.apply_font(st["font_family"], st["font_size"], st["line_spacing"])
    cl.addWidget(reader, 1)

    # Нижняя строка
    status_lbl = QLabel("Открой книгу из списка слева")
    status_lbl.setFixedHeight(24)
    status_lbl.setStyleSheet("""
        background: rgba(0,0,0,0.30);
        color: rgba(255,255,255,0.55);
        font-size: 11px;
        padding: 3px 12px;
        border-top: 1px solid rgba(255,255,255,0.06);
    """)
    cl.addWidget(status_lbl)

    h.addWidget(center, 1)

    # ============================================================
    #  Правая панель — настройки
    # ============================================================
    right = QWidget()
    right.setFixedWidth(260)
    right.setStyleSheet("""
        background: rgba(255,255,255,0.04);
        border-left: 1px solid rgba(255,255,255,0.08);
    """)
    rl = QVBoxLayout(right)
    rl.setContentsMargins(16, 20, 16, 20)
    rl.setSpacing(12)

    settings_title = QLabel("⚙  Настройки чтения")
    settings_title.setStyleSheet("color: white; font-size: 14px; font-weight: 600;")
    rl.addWidget(settings_title)

    # Тема
    theme_lbl = QLabel("ТЕМА")
    theme_lbl.setStyleSheet("""
        color: rgba(255,255,255,0.45);
        font-size: 10px;
        font-weight: 700;
        letter-spacing: 1.5px;
        padding-top: 6px;
    """)
    rl.addWidget(theme_lbl)

    theme_row = QHBoxLayout()
    theme_row.setSpacing(6)

    theme_buttons = {}
    for key, data in THEMES.items():
        b = QPushButton()
        b.setFixedSize(48, 36)
        b.setCursor(Qt.PointingHandCursor)
        b.setToolTip(data["name"])
        b.setStyleSheet(f"""
            QPushButton {{
                background: {data['bg']};
                color: {data['fg']};
                border: 2px solid rgba(255,255,255,0.15);
                border-radius: 8px;
                font-size: 11px;
            }}
            QPushButton:hover {{
                border: 2px solid {data['accent']};
            }}
        """)
        b.setText(data["name"][0])
        b.clicked.connect(lambda _, k=key: set_theme(k))
        theme_row.addWidget(b)
        theme_buttons[key] = b

    theme_row.addStretch(1)
    rl.addLayout(theme_row)

    # Шрифт
    font_lbl = QLabel("ШРИФТ")
    font_lbl.setStyleSheet(theme_lbl.styleSheet())
    rl.addWidget(font_lbl)

    font_combo = QFontComboBox()
    font_combo.setCurrentFont(QFont("Georgia"))
    font_combo.setStyleSheet("""
        QFontComboBox {
            background: rgba(255,255,255,0.08);
            color: white;
            border: 1px solid rgba(255,255,255,0.15);
            border-radius: 10px;
            padding: 6px 10px;
            font-size: 12px;
        }
    """)
    rl.addWidget(font_combo)

    # Размер шрифта
    size_row = QHBoxLayout()
    size_lbl = QLabel("Размер:")
    size_lbl.setStyleSheet("color: rgba(255,255,255,0.75); font-size: 12px;")
    size_row.addWidget(size_lbl)

    size_slider = QSlider(Qt.Horizontal)
    size_slider.setRange(10, 32)
    size_slider.setValue(st["font_size"])
    size_slider.setStyleSheet("""
        QSlider::groove:horizontal {
            height: 4px;
            background: rgba(255,255,255,0.15);
            border-radius: 2px;
        }
        QSlider::sub-page:horizontal {
            background: #6EC6FF;
            border-radius: 2px;
        }
        QSlider::handle:horizontal {
            background: white;
            width: 12px;
            margin: -4px 0;
            border-radius: 6px;
        }
    """)
    size_row.addWidget(size_slider, 1)

    size_val = QLabel(str(st["font_size"]))
    size_val.setFixedWidth(30)
    size_val.setAlignment(Qt.AlignRight)
    size_val.setStyleSheet("color: white; font-size: 12px; font-weight: 600;")
    size_row.addWidget(size_val)

    rl.addLayout(size_row)

    # Межстрочный интервал
    ls_row = QHBoxLayout()
    ls_lbl = QLabel("Интервал:")
    ls_lbl.setStyleSheet(size_lbl.styleSheet())
    ls_row.addWidget(ls_lbl)

    ls_slider = QSlider(Qt.Horizontal)
    ls_slider.setRange(10, 25)   # 1.0 .. 2.5
    ls_slider.setValue(int(st["line_spacing"] * 10))
    ls_slider.setStyleSheet(size_slider.styleSheet())
    ls_row.addWidget(ls_slider, 1)

    ls_val = QLabel(f"{st['line_spacing']:.1f}")
    ls_val.setFixedWidth(30)
    ls_val.setAlignment(Qt.AlignRight)
    ls_val.setStyleSheet(size_val.styleSheet())
    ls_row.addWidget(ls_val)

    rl.addLayout(ls_row)

    rl.addSpacing(10)

    # Оглавление (для MD/FB2)
    toc_lbl = QLabel("ОГЛАВЛЕНИЕ")
    toc_lbl.setStyleSheet(theme_lbl.styleSheet())
    rl.addWidget(toc_lbl)

    toc_list = QListWidget()
    toc_list.setStyleSheet("""
        QListWidget {
            background: rgba(0,0,0,0.20);
            color: white;
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 10px;
            padding: 4px;
            font-size: 11px;
            outline: none;
        }
        QListWidget::item { padding: 6px 8px; border-radius: 6px; }
        QListWidget::item:hover { background: rgba(255,255,255,0.08); }
        QListWidget::item:selected { background: rgba(110,198,255,0.30); }
    """)
    rl.addWidget(toc_list, 1)

    h.addWidget(right)

    # ============================================================
    #  Логика
    # ============================================================

    def scan_books():
        book_list.clear()
        if vfs is None:
            return
        files = []

        def walk(path, depth=0):
            if depth > 6:
                return
            try:
                items = vfs.listdir(path)
            except Exception:
                return
            for it in items:
                if it["is_dir"]:
                    walk(it["path"], depth + 1)
                else:
                    name_low = it["name"].lower()
                    if name_low.endswith((".txt", ".md", ".log",
                                          ".fb2", ".csv")):
                        files.append(it)

        walk("/")

        query = search_books.text().strip().lower()
        for f in files:
            name = f["name"]
            if query and query not in name.lower():
                continue
            item = QListWidgetItem(f"📖 {name}")
            item.setData(Qt.UserRole, f["path"])
            book_list.addItem(item)

    def open_book(path: str, title: str = ""):
        text = load_book_text(vfs, path)
        if not text.strip():
            QMessageBox.warning(root, "Читалка",
                "Не удалось загрузить текст книги\n"
                "(файл пустой или нечитаемый).")
            return

        st["book_path"] = path
        st["book_title"] = title or os.path.basename(path)
        st["book_text"] = text

        reader.setPlainText(text)
        book_title_lbl.setText(st["book_title"])

        # Восстанавливаем прогресс
        prog = store.get_progress(path)
        scroll = prog.get("scroll", 0)
        QTimer.singleShot(100, lambda: reader.verticalScrollBar().setValue(scroll))

        # Загружаем закладки
        refresh_bookmarks()

        # Строим оглавление
        build_toc(text)

        # Обновляем прогресс
        update_progress()

        if desktop and hasattr(desktop, "notifications"):
            desktop.notifications.push("Открыта книга", st["book_title"])

    def build_toc(text: str):
        toc_list.clear()
        # Ищем заголовки (например, строки в верхнем регистре или после ═)
        lines = text.split("\n")
        for i, line in enumerate(lines):
            line_s = line.strip()
            # Заголовок — если следующая строка из ═ или ─
            if i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                if (next_line.startswith("═") or next_line.startswith("─")) and len(next_line) > 3:
                    if line_s and len(line_s) < 100:
                        item = QListWidgetItem(f"📄 {line_s}")
                        item.setData(Qt.UserRole, i)
                        toc_list.addItem(item)

        if toc_list.count() == 0:
            toc_list.addItem(QListWidgetItem("(нет заголовков)"))

    def jump_to_line(line_idx: int):
        # Находим блок по номеру строки
        block = reader.document().findBlockByLineNumber(line_idx)
        if block.isValid():
            cursor = reader.textCursor()
            cursor.setPosition(block.position())
            reader.setTextCursor(cursor)
            reader.ensureCursorVisible()

    def update_progress():
        if not st["book_path"]:
            return
        sb = reader.verticalScrollBar()
        total = max(1, sb.maximum())
        percent = int(sb.value() / total * 100)
        status_lbl.setText(
            f"{st['book_title']}  ·  {percent}%  ·  "
            f"{len(st['book_text'])} символов")

        # Обновляем полоску прогресса
        progress_inner.setGeometry(
            0, 0,
            int(progress_bar.width() * percent / 100),
            3)

    def save_progress():
        if not st["book_path"]:
            return
        sb = reader.verticalScrollBar()
        store.set_progress(st["book_path"], sb.value())

    # Автосохранение прогресса
    progress_timer = QTimer(root)
    progress_timer.setInterval(2000)
    progress_timer.timeout.connect(save_progress)
    progress_timer.start()

    # Обновление при прокрутке
    reader.verticalScrollBar().valueChanged.connect(update_progress)

    def set_theme(key: str):
        if key not in THEMES:
            return
        st["theme"] = key
        reader.apply_theme(THEMES[key])
        # Обновляем выделение в кнопках
        for k, b in theme_buttons.items():
            border = "3px solid white" if k == key else "2px solid rgba(255,255,255,0.15)"
            b.setStyleSheet(f"""
                QPushButton {{
                    background: {THEMES[k]['bg']};
                    color: {THEMES[k]['fg']};
                    border: {border};
                    border-radius: 8px;
                    font-size: 11px;
                }}
            """)

    def set_font():
        family = font_combo.currentFont().family()
        size = size_slider.value()
        spacing = ls_slider.value() / 10.0
        st["font_family"] = family
        st["font_size"] = size
        st["line_spacing"] = spacing
        reader.apply_font(family, size, spacing)
        size_val.setText(str(size))
        ls_val.setText(f"{spacing:.1f}")

    font_combo.currentFontChanged.connect(lambda _: set_font())
    size_slider.valueChanged.connect(lambda _: set_font())
    ls_slider.valueChanged.connect(lambda _: set_font())

    # ============================================================
    #  Поиск по тексту
    # ============================================================

    def do_search():
        query = search_input.text().strip()
        if not query or not st["book_text"]:
            st["search_results"] = []
            return
        text_lower = st["book_text"].lower()
        q_lower = query.lower()
        results = []
        idx = 0
        while True:
            idx = text_lower.find(q_lower, idx)
            if idx == -1:
                break
            results.append(idx)
            idx += len(q_lower)
        st["search_results"] = results
        st["search_index"] = 0
        st["last_search"] = query
        if results:
            status_lbl.setText(
                f"Найдено: {len(results)} совпадений  ·  "
                f"{st['search_index'] + 1} / {len(results)}")
            highlight_current_match()

    def highlight_current_match():
        if not st["search_results"]:
            return
        pos = st["search_results"][st["search_index"]]
        q_len = len(st["last_search"])

        cursor = reader.textCursor()
        cursor.setPosition(pos)
        cursor.setPosition(pos + q_len, QTextCursor.KeepAnchor)
        reader.setTextCursor(cursor)
        reader.ensureCursorVisible()

        status_lbl.setText(
            f"Найдено: {len(st['search_results'])}  ·  "
            f"{st['search_index'] + 1} / {len(st['search_results'])}")

    def next_match():
        if not st["search_results"]:
            return
        st["search_index"] = (st["search_index"] + 1) % len(st["search_results"])
        highlight_current_match()

    def prev_match():
        if not st["search_results"]:
            return
        st["search_index"] = (st["search_index"] - 1) % len(st["search_results"])
        highlight_current_match()

    search_input.returnPressed.connect(do_search)
    search_input.textChanged.connect(do_search)
    search_next.clicked.connect(next_match)
    search_prev.clicked.connect(prev_match)

    # ============================================================
    #  Закладки
    # ============================================================

    def refresh_bookmarks():
        bookmarks_list.clear()
        if not st["book_path"]:
            return
        bms = store.get_bookmarks(st["book_path"])
        for i, bm in enumerate(bms):
            item = QListWidgetItem(f"🔖 {bm['name']}")
            item.setData(Qt.UserRole, i)
            item.setToolTip(time.strftime(
                "%d.%m.%Y %H:%M", time.localtime(bm["added"])))
            bookmarks_list.addItem(item)
        if not bms:
            item = QListWidgetItem("(нет закладок)")
            item.setFlags(Qt.NoItemFlags)
            bookmarks_list.addItem(item)

    def add_bookmark():
        if not st["book_path"]:
            return
        name, ok = QInputDialog.getText(
            root, "Новая закладка",
            "Название:",
            text=f"Строка {reader.textCursor().blockNumber() + 1}")
        if not ok or not name.strip():
            return
        pos = reader.verticalScrollBar().value()
        store.add_bookmark(st["book_path"], name.strip(), pos)
        refresh_bookmarks()

    def goto_bookmark(item):
        idx = item.data(Qt.UserRole)
        if idx is None:
            return
        bms = store.get_bookmarks(st["book_path"])
        if 0 <= idx < len(bms):
            reader.verticalScrollBar().setValue(bms[idx]["position"])
            reader.ensureCursorVisible()

    add_bm_btn.clicked.connect(add_bookmark)
    bookmarks_list.itemDoubleClicked.connect(goto_bookmark)

    # Контекстное меню для закладок
    def bm_context(pos):
        item = bookmarks_list.itemAt(pos)
        if item is None:
            return
        idx = item.data(Qt.UserRole)
        if idx is None:
            return
        menu = make_menu(bookmarks_list)
        a_del = menu.addAction("🗑 Удалить закладку")
        def do_del():
            store.remove_bookmark(st["book_path"], idx)
            refresh_bookmarks()
        a_del.triggered.connect(do_del)
        menu.exec(bookmarks_list.mapToGlobal(pos))

    bookmarks_list.setContextMenuPolicy(Qt.CustomContextMenu)
    bookmarks_list.customContextMenuRequested.connect(bm_context)

    # ============================================================
    #  Горячие клавиши
    # ============================================================

    def sc(seq, cb):
        s = QShortcut(QKeySequence(seq), root)
        s.setContext(Qt.WidgetWithChildrenShortcut)
        s.activated.connect(cb)

    def next_page():
        sb = reader.verticalScrollBar()
        sb.setValue(sb.value() + sb.pageStep())

    def prev_page():
        sb = reader.verticalScrollBar()
        sb.setValue(sb.value() - sb.pageStep())

    sc("Ctrl+B", add_bookmark)
    sc("Ctrl+F", lambda: search_input.setFocus())
    sc("Right", next_page)
    sc("Left", prev_page)
    sc("PageDown", next_page)
    sc("PageUp", prev_page)
    sc("Ctrl+Right", next_match)
    sc("Ctrl+Left", prev_match)
    sc("F3", next_match)
    sc("Shift+F3", prev_match)

    # ============================================================
    #  Обработчики
    # ============================================================

    def on_book_click(item):
        path = item.data(Qt.UserRole)
        if path:
            title = item.text().replace("📖 ", "")
            open_book(path, title)

    book_list.itemClicked.connect(on_book_click)
    search_books.textChanged.connect(scan_books)

    def on_toc_click(item):
        line_idx = item.data(Qt.UserRole)
        if line_idx is not None:
            jump_to_line(line_idx)

    toc_list.itemClicked.connect(on_toc_click)

    # ---- Автосохранение прогресса при закрытии ----
    def on_close():
        save_progress()

    root.destroyed.connect(on_close)

    # ============================================================
    #  Старт
    # ============================================================

    scan_books()
    set_theme("dark")

    # Автооткрытие книги, если она одна
    if book_list.count() == 1:
        item = book_list.item(0)
        open_book(item.data(Qt.UserRole),
                   item.text().replace("📖 ", ""))

    return root