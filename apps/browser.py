"""
MountOS — Браузер.

Полноценный веб-браузер на QtWebEngine (Chromium):
  • Вкладки (лимит 8 для производительности)
  • Адресная строка (URL или поиск Google)
  • Навигация: назад / вперёд / обновить / домой
  • Прогресс загрузки
  • Закладки (сохраняются в VFS)
  • История посещений (сохраняется в VFS)
  • Скачивание в VFS /Downloads/ (перехват WebEngine)
  • Горячие клавиши (через eventFilter — не мешают странице)

Оптимизации:
  • Ограниченный кэш (50 МБ)
  • GPU-ускорение (флаги в main.py)
  • Прогрев Chromium при старте MountOS
  • Лимит вкладок
"""
import json
import os
import shutil
import tempfile

from PySide6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QLabel,
                                QPushButton, QLineEdit, QTabWidget, QToolButton,
                                QMenu, QMessageBox, QSizePolicy, QProgressBar,
                                QInputDialog)
from PySide6.QtCore import Qt, QUrl, QSize, QTimer, Signal, QEvent
from PySide6.QtGui import QIcon, QAction, QKeySequence, QShortcut, QKeyEvent

from ui.icons import get_icon
from ui.settings_state import state
from ui.context_menu import make_menu

APP_NAME = "Браузер"
APP_ICON = "browser"
APP_VERSION = "1.2"
APP_AUTHOR = "MountOS"


HOME_URL = "https://www.google.com"
SEARCH_URL = "https://www.google.com/search?q={}"
MAX_TABS = 8


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
#  URL-утилиты
# ============================================================

def _normalize_url(text: str) -> QUrl:
    text = text.strip()
    if not text:
        return QUrl(HOME_URL)
    if text.startswith(("http://", "https://", "file://", "ftp://")):
        return QUrl(text)
    if "." in text and " " not in text:
        return QUrl("https://" + text)
    from urllib.parse import quote_plus
    return QUrl(SEARCH_URL.format(quote_plus(text)))


# ============================================================
#  Хранилище
# ============================================================

class BrowserStore:
    HISTORY_PATH = "/Notes/browser_history.json"
    BOOKMARKS_PATH = "/Notes/browser_bookmarks.json"
    MAX_HISTORY = 200

    def __init__(self, vfs):
        self.vfs = vfs
        self.history = self._load(self.HISTORY_PATH, [])
        self.bookmarks = self._load(self.BOOKMARKS_PATH, [])

    def _load(self, path, default):
        if self.vfs is None:
            return default
        try:
            raw = self.vfs.read_text(path, "")
            if not raw.strip():
                return default
            data = json.loads(raw)
            return data if isinstance(data, list) else default
        except Exception:
            return default

    def _save(self, path, data):
        if self.vfs is None:
            return
        try:
            self.vfs.write_text(path, json.dumps(data, ensure_ascii=False, indent=2))
        except Exception as e:
            print(f"[Browser] save error: {e}")

    def add_history(self, url: str, title: str = ""):
        if not url:
            return
        self.history = [h for h in self.history if h.get("url") != url]
        self.history.append({"url": url, "title": title})
        if len(self.history) > self.MAX_HISTORY:
            self.history = self.history[-self.MAX_HISTORY:]
        self._save(self.HISTORY_PATH, self.history)

    def is_bookmarked(self, url: str) -> bool:
        return any(b.get("url") == url for b in self.bookmarks)

    def add_bookmark(self, url: str, title: str = ""):
        if self.is_bookmarked(url):
            return
        self.bookmarks.append({"url": url, "title": title})
        self._save(self.BOOKMARKS_PATH, self.bookmarks)

    def remove_bookmark(self, url: str):
        self.bookmarks = [b for b in self.bookmarks if b.get("url") != url]
        self._save(self.BOOKMARKS_PATH, self.bookmarks)

    def clear_history(self):
        self.history = []
        self._save(self.HISTORY_PATH, self.history)


# ============================================================
#  Основное приложение
# ============================================================

def build():
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWebEngineCore import QWebEngineProfile

    root = QWidget()
    root_layout = QVBoxLayout(root)
    root_layout.setContentsMargins(0, 0, 0, 0)
    root_layout.setSpacing(0)

    vfs = _get_vfs(root)
    desktop = _get_desktop(root)
    store = BrowserStore(vfs)

    # ---------- Верхняя панель ----------
    top = QWidget()
    top.setStyleSheet("""
        background: rgba(255,255,255,0.04);
        border-bottom: 1px solid rgba(255,255,255,0.08);
    """)
    top.setFixedHeight(48)
    tl = QHBoxLayout(top)
    tl.setContentsMargins(10, 6, 10, 6)
    tl.setSpacing(6)

    def icon_btn(icon_name, tooltip, callback, size=32):
        b = QPushButton()
        b.setFixedSize(size, size)
        b.setToolTip(tooltip)
        b.setCursor(Qt.PointingHandCursor)
        b.setIcon(QIcon(get_icon(icon_name, 18, "#FFFFFF")))
        b.setIconSize(QSize(16, 16))
        b.setStyleSheet("""
            QPushButton {
                background: rgba(255,255,255,0.06);
                border: 1px solid rgba(255,255,255,0.10);
                border-radius: 8px;
            }
            QPushButton:hover { background: rgba(255,255,255,0.18); }
            QPushButton:pressed { background: rgba(110,198,255,0.35); }
            QPushButton:disabled { background: rgba(255,255,255,0.02); }
        """)
        b.clicked.connect(callback)
        return b

    back_btn = icon_btn("back", "Назад (Alt+←)", lambda: _nav("back"))
    tl.addWidget(back_btn)

    fwd_btn = icon_btn("forward", "Вперёд (Alt+→)", lambda: _nav("forward"))
    tl.addWidget(fwd_btn)

    reload_btn = icon_btn("reload", "Обновить (F5 / Ctrl+R)", lambda: _nav("reload"))
    tl.addWidget(reload_btn)

    home_btn = icon_btn("home", "Домой", lambda: _nav("home"))
    tl.addWidget(home_btn)

    url_edit = QLineEdit()
    url_edit.setPlaceholderText("Введи URL или поисковый запрос…")
    url_edit.setStyleSheet("""
        QLineEdit {
            background: rgba(255,255,255,0.08);
            color: white;
            border: 1px solid rgba(255,255,255,0.15);
            border-radius: 10px;
            padding: 8px 14px;
            font-size: 13px;
            font-family: 'Segoe UI', sans-serif;
        }
        QLineEdit:focus {
            border: 1px solid rgba(110,198,255,0.75);
            background: rgba(255,255,255,0.12);
        }
    """)
    tl.addWidget(url_edit, 1)

    star_btn = icon_btn("star", "Добавить в закладки (Ctrl+D)", lambda: _toggle_bookmark())
    tl.addWidget(star_btn)

    menu_btn = icon_btn("grid", "Меню", lambda: _show_menu())
    tl.addWidget(menu_btn)

    new_tab_btn = icon_btn("plus", "Новая вкладка (Ctrl+T)", lambda: _new_tab())
    tl.addWidget(new_tab_btn)

    root_layout.addWidget(top)

    # ---------- Прогресс-бар ----------
    progress = QProgressBar()
    progress.setFixedHeight(2)
    progress.setTextVisible(False)
    progress.setRange(0, 100)
    progress.setValue(0)
    progress.setStyleSheet("""
        QProgressBar {
            background: transparent;
            border: none;
        }
        QProgressBar::chunk {
            background: #6EC6FF;
        }
    """)
    root_layout.addWidget(progress)

    # ---------- Вкладки ----------
    tabs = QTabWidget()
    tabs.setTabsClosable(True)
    tabs.setMovable(True)
    tabs.setDocumentMode(True)
    tabs.setStyleSheet("""
        QTabWidget::pane {
            background: white;
            border: none;
        }
        QTabBar {
            background: rgba(255,255,255,0.02);
        }
        QTabBar::tab {
            background: rgba(255,255,255,0.05);
            color: rgba(255,255,255,0.70);
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 8px;
            padding: 6px 12px;
            margin: 4px 2px;
            font-size: 11px;
            min-width: 120px;
            max-width: 220px;
        }
        QTabBar::tab:selected {
            background: rgba(110,198,255,0.22);
            color: white;
            border: 1px solid rgba(110,198,255,0.50);
        }
        QTabBar::tab:hover:!selected {
            background: rgba(255,255,255,0.12);
            color: white;
        }
    """)
    tabs.tabCloseRequested.connect(lambda idx: _close_tab(idx))
    tabs.currentChanged.connect(lambda idx: _on_tab_changed(idx))

    root_layout.addWidget(tabs, 1)

    # ============================================================
    #  Настройка профиля для скорости
    # ============================================================

    def _on_download(download):
        try:
            suggested = download.downloadFileName()
            tmp_dir = tempfile.gettempdir()
            tmp_path = os.path.join(tmp_dir, f"mountos_dl_{suggested}")
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass

            download.setDownloadDirectory(tmp_dir)
            download.setDownloadFileName(os.path.basename(tmp_path))
            download.accept()

            if desktop and hasattr(desktop, "notifications"):
                desktop.notifications.push("Скачивание", f"{suggested} — началось")

            def _on_state(state_val):
                from PySide6.QtWebEngineCore import QWebEngineDownloadRequest
                if state_val == QWebEngineDownloadRequest.DownloadCompleted:
                    _move_to_vfs(tmp_path, suggested)
                elif state_val == QWebEngineDownloadRequest.DownloadInterrupted:
                    print(f"[Browser] скачивание прервано: {suggested}")
                    _cleanup(tmp_path)

            download.stateChanged.connect(_on_state)
        except Exception as e:
            print(f"[Browser] ошибка обработки скачивания: {e}")

    def _move_to_vfs(src_path: str, original_name: str):
        try:
            if vfs is None:
                print("[Browser] VFS недоступна")
                return
            vfs.mkdir("/Downloads")
            with open(src_path, "rb") as f:
                data = f.read()
            vfs_path = vfs.join("/Downloads", original_name)
            base, dot, ext = original_name.partition(".")
            n = 1
            while vfs.exists(vfs_path):
                vfs_path = vfs.join("/Downloads", f"{base}_{n}{dot}{ext}")
                n += 1
            vfs.write_bytes(vfs_path, data)
            size_kb = len(data) / 1024
            if desktop and hasattr(desktop, "notifications"):
                desktop.notifications.push(
                    "Скачано",
                    f"{os.path.basename(vfs_path)} ({size_kb:.0f} КБ) → /Downloads/")
            print(f"[Browser] скачано в VFS: {vfs_path}")
        except Exception as e:
            print(f"[Browser] ошибка копирования в VFS: {e}")
            if desktop and hasattr(desktop, "notifications"):
                desktop.notifications.push(
                    "Ошибка скачивания",
                    f"Не удалось сохранить {original_name}: {e}")
        finally:
            _cleanup(src_path)

    def _cleanup(path: str):
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception:
            pass

    # Настройка профиля
    try:
        profile = QWebEngineProfile.defaultProfile()
        # Лимит кэша 50 МБ — не растёт бесконечно
        profile.setHttpCacheType(QWebEngineProfile.MemoryHttpCache)
        profile.setHttpCacheMaximumSize(50 * 1024 * 1024)
        profile.setPersistentCookiesPolicy(QWebEngineProfile.ForcePersistentCookies)
        profile.setHttpUserAgent(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36")
        profile.downloadRequested.connect(_on_download)
    except Exception as e:
        print(f"[Browser] profile setup: {e}")

    # ============================================================
    #  Логика вкладок
    # ============================================================

    def current_view():
        return tabs.currentWidget()

    def _nav(action):
        view = current_view()
        if view is None:
            return
        if action == "back":
            view.back()
        elif action == "forward":
            view.forward()
        elif action == "reload":
            view.reload()
        elif action == "home":
            view.setUrl(QUrl(HOME_URL))

    def _new_tab(url: str = None):
        # Лимит вкладок
        while tabs.count() >= MAX_TABS:
            closed = False
            for i in range(tabs.count()):
                if i != tabs.currentIndex():
                    _close_tab(i)
                    closed = True
                    break
            if not closed:
                break

        view = QWebEngineView()
        idx = tabs.addTab(view, "Новая вкладка")
        tabs.setCurrentIndex(idx)

        view.urlChanged.connect(lambda u, v=view: _on_url_changed(v, u))
        view.titleChanged.connect(lambda t, v=view: _on_title_changed(v, t))
        view.loadProgress.connect(lambda p, v=view: _on_load_progress(v, p))
        view.loadFinished.connect(lambda ok, v=view: _on_load_finished(v, ok))

        view.setUrl(QUrl(url or HOME_URL))
        QTimer.singleShot(50, view.setFocus)
        return view

    def _on_url_changed(view, url: QUrl):
        if view is current_view():
            url_edit.setText(url.toString())
            url_edit.setCursorPosition(0)
            back_btn.setEnabled(view.history().canGoBack())
            fwd_btn.setEnabled(view.history().canGoForward())
            _refresh_star(view, url.toString())

    def _on_title_changed(view, title):
        idx = tabs.indexOf(view)
        if idx < 0:
            return
        if not title:
            title = "Новая вкладка"
        if len(title) > 30:
            title = title[:28] + "…"
        tabs.setTabText(idx, title)
        url = view.url().toString()
        if url and url != "about:blank":
            store.add_history(url, title)

    def _on_load_progress(view, p):
        if view is current_view():
            if p < 100:
                progress.setValue(p)
                progress.show()
            else:
                progress.setValue(100)
                QTimer.singleShot(300, lambda: progress.hide())

    def _on_load_finished(view, ok):
        if view is current_view() and ok:
            progress.hide()

    def _on_tab_changed(idx):
        view = tabs.widget(idx)
        if view is None:
            return
        url = view.url().toString()
        url_edit.setText(url)
        back_btn.setEnabled(view.history().canGoBack())
        fwd_btn.setEnabled(view.history().canGoForward())
        _refresh_star(view, url)
        QTimer.singleShot(50, view.setFocus)

    def _close_tab(idx):
        if tabs.count() <= 1:
            view = tabs.widget(0)
            if view:
                view.setUrl(QUrl(HOME_URL))
            return
        w = tabs.widget(idx)
        tabs.removeTab(idx)
        if w:
            w.deleteLater()

    def _refresh_star(view, url: str):
        if store.is_bookmarked(url):
            star_btn.setIcon(QIcon(get_icon("star_filled", 18, "#FFB86C")))
        else:
            star_btn.setIcon(QIcon(get_icon("star", 18, "#FFFFFF")))

    def _toggle_bookmark():
        view = current_view()
        if view is None:
            return
        url = view.url().toString()
        if not url:
            return
        title = view.title() or url
        if store.is_bookmarked(url):
            store.remove_bookmark(url)
        else:
            store.add_bookmark(url, title)
        _refresh_star(view, url)

    def _show_menu():
        menu = make_menu(root)

        sub_b = menu.addMenu("⭐  Закладки")
        sub_b.setStyleSheet(menu.styleSheet())
        if store.bookmarks:
            for bm in reversed(store.bookmarks[-15:]):
                a = QAction(bm.get("title", bm["url"])[:60], sub_b)
                a.triggered.connect(lambda _, u=bm["url"]: _new_tab(u))
                sub_b.addAction(a)
            sub_b.addSeparator()
            a_clear = QAction("Очистить закладки", sub_b)
            a_clear.triggered.connect(lambda: _clear_bookmarks())
            sub_b.addAction(a_clear)
        else:
            a_empty = QAction("Пусто", sub_b)
            a_empty.setEnabled(False)
            sub_b.addAction(a_empty)

        sub_h = menu.addMenu("🕒  История")
        sub_h.setStyleSheet(menu.styleSheet())
        if store.history:
            for h in reversed(store.history[-15:]):
                a = QAction(h.get("title", h["url"])[:60], sub_h)
                a.triggered.connect(lambda _, u=h["url"]: _new_tab(u))
                sub_h.addAction(a)
            sub_h.addSeparator()
            a_clear_h = QAction("Очистить историю", sub_h)
            a_clear_h.triggered.connect(lambda: _clear_history())
            sub_h.addAction(a_clear_h)
        else:
            a_empty = QAction("Пусто", sub_h)
            a_empty.setEnabled(False)
            sub_h.addAction(a_empty)

        menu.addSeparator()

        a_new = menu.addAction("➕  Новая вкладка")
        a_new.triggered.connect(lambda: _new_tab())

        a_home = menu.addAction("🏠  Домой")
        a_home.triggered.connect(lambda: _nav("home"))

        menu.addSeparator()

        a_dl = menu.addAction("📁  Открыть папку загрузок")
        a_dl.triggered.connect(lambda: _open_downloads())

        menu.exec(menu_btn.mapToGlobal(menu_btn.rect().bottomLeft()))

    def _open_downloads():
        if desktop and hasattr(desktop, "open_app"):
            desktop.open_app("files")

    def _clear_history():
        ans = QMessageBox.question(root, "История",
            "Очистить историю браузера?", QMessageBox.Yes | QMessageBox.No)
        if ans == QMessageBox.Yes:
            store.clear_history()

    def _clear_bookmarks():
        ans = QMessageBox.question(root, "Закладки",
            "Удалить все закладки?", QMessageBox.Yes | QMessageBox.No)
        if ans == QMessageBox.Yes:
            store.bookmarks = []
            store._save(store.BOOKMARKS_PATH, [])
            v = current_view()
            if v:
                _refresh_star(v, v.url().toString())

    def _on_url_enter():
        text = url_edit.text().strip()
        if not text:
            return
        view = current_view()
        if view is None:
            view = _new_tab()
        view.setUrl(_normalize_url(text))
        QTimer.singleShot(50, view.setFocus)

    url_edit.returnPressed.connect(_on_url_enter)
    # ============================================================
    #  Горячие клавиши через eventFilter
    #  (перехватывают только когда фокус НЕ в адресной строке)
    # ============================================================

    from PySide6.QtCore import QObject

    class _BrowserShortcutFilter(QObject):
        """Фильтр событий браузера. Наследник QObject — обязателен для Qt."""

        def __init__(self, parent=None):
            super().__init__(parent)

        def eventFilter(self, obj, event):
            if event.type() != QEvent.KeyPress:
                return False
            # Если фокус в адресной строке — не перехватываем
            if url_edit.hasFocus():
                return False

            ctrl = bool(event.modifiers() & Qt.ControlModifier)
            alt = bool(event.modifiers() & Qt.AltModifier)
            key = event.key()

            if ctrl and key == Qt.Key_T:
                _new_tab()
                return True
            if ctrl and key == Qt.Key_W:
                _close_tab(tabs.currentIndex())
                return True
            if ctrl and key == Qt.Key_R:
                _nav("reload")
                return True
            if key == Qt.Key_F5 and not ctrl and not alt:
                _nav("reload")
                return True
            if ctrl and key == Qt.Key_L:
                url_edit.setFocus()
                url_edit.selectAll()
                return True
            if alt and key == Qt.Key_Left:
                _nav("back")
                return True
            if alt and key == Qt.Key_Right:
                _nav("forward")
                return True
            if ctrl and key == Qt.Key_D:
                _toggle_bookmark()
                return True

            return False

    # ВАЖНО: фильтр должен жить всё время работы окна,
    # иначе Qt его удалит и он перестанет работать.
    root._browser_filter = _BrowserShortcutFilter(root)
    root.installEventFilter(root._browser_filter)

    # ---------- Первая вкладка ----------
    _new_tab()

    return root