"""
MountOS — Spotlight (глобальный поиск).

Открывается по Ctrl+Space.
Ищет: приложения, файлы VFS, быстрые действия.
"""
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                                QLineEdit, QListWidget, QListWidgetItem,
                                QGraphicsDropShadowEffect, QApplication)
from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve, Signal, QSize
from PySide6.QtGui import QIcon, QColor

from ui.icons import get_icon
from ui.settings_state import state


class Spotlight(QWidget):
    """Плавающее окно поиска по центру экрана."""

    app_launch_requested = Signal(str)
    file_open_requested = Signal(str)
    action_requested = Signal(str)

    def __init__(self, host: QWidget):
        super().__init__(host)
        self.host = host
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.hide()

        self._visible = False
        self._registry = None

        self.setFixedWidth(640)
        self.setFixedHeight(460)

        # Внешний layout
        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 10)
        outer.setSpacing(0)

        # Стеклянная карточка
        card = QWidget(self)
        card.setObjectName("spotCard")
        card.setStyleSheet("""
            QWidget#spotCard {
                background: rgba(22, 28, 44, 0.98);
                border: 1px solid rgba(255,255,255,0.14);
                border-radius: 22px;
            }
        """)
        outer.addWidget(card)

        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(60)
        shadow.setOffset(0, 20)
        shadow.setColor(QColor(0, 0, 0, 200))
        card.setGraphicsEffect(shadow)

        cl = QVBoxLayout(card)
        cl.setContentsMargins(18, 16, 18, 14)
        cl.setSpacing(10)

        # Верх: иконка + поиск
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(12)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(get_icon("globe", 22, state().get("accent")))
        icon_lbl.setFixedSize(24, 24)
        icon_lbl.setStyleSheet("background: transparent; border: none;")
        top.addWidget(icon_lbl)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Поиск приложений, файлов и действий…")
        self.search.setStyleSheet("""
            QLineEdit {
                background: transparent;
                color: white;
                border: none;
                padding: 4px 0;
                font-size: 18px;
                font-weight: 300;
            }
        """)
        self.search.textChanged.connect(self._update_results)
        self.search.returnPressed.connect(self._activate_current)
        top.addWidget(self.search, 1)

        cl.addLayout(top)

        # Разделитель
        sep = QWidget()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: rgba(255,255,255,0.08);")
        cl.addWidget(sep)

        # Список результатов
        self.listw = QListWidget()
        self.listw.setStyleSheet("""
            QListWidget {
                background: transparent;
                border: none;
                outline: none;
                color: white;
                font-size: 13px;
                padding: 4px 0;
            }
            QListWidget::item {
                padding: 10px 12px;
                border-radius: 10px;
                margin: 1px 0;
            }
            QListWidget::item:hover { background: rgba(255,255,255,0.06); }
            QListWidget::item:selected {
                background: rgba(110,198,255,0.28);
                color: white;
            }
        """)
        self.listw.itemActivated.connect(lambda _: self._activate_current())
        self.listw.itemClicked.connect(lambda _: self._activate_current())
        cl.addWidget(self.listw, 1)

        # Подсказки
        hint = QLabel("↑ ↓  выбрать      Enter  открыть      Esc  закрыть")
        hint.setStyleSheet("""
            color: rgba(255,255,255,0.35);
            font-size: 11px;
            padding: 2px 4px;
        """)
        cl.addWidget(hint)

        self._results = []

    # ------------------------------------------------------------
    #  Registry
    # ------------------------------------------------------------

    def set_registry(self, registry):
        self._registry = registry

    # ------------------------------------------------------------
    #  Показ / скрытие
    # ------------------------------------------------------------

    def show_spotlight(self):
        if self._visible:
            return

        self._reposition()
        self.search.clear()
        self._update_results("")
        if self.listw.count() > 0:
            self.listw.setCurrentRow(0)

        # Принудительная перерисовка (фикс «двойного» окна)
        self.setGeometry(self.geometry())
        self.update()
        self.repaint()

        self.show()
        self.raise_()
        self.activateWindow()
        self.search.setFocus()

        # Плавное появление
        self.setWindowOpacity(0.0)
        anim = QPropertyAnimation(self, b"windowOpacity")
        anim.setDuration(180)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.start()
        self._anim = anim

        self._visible = True

    def hide_spotlight(self):
        if not self._visible:
            return
        anim = QPropertyAnimation(self, b"windowOpacity")
        anim.setDuration(140)
        anim.setEasingCurve(QEasingCurve.InCubic)
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        anim.finished.connect(self._after_hide)
        anim.start()
        self._anim = anim
        self._visible = False

    def _after_hide(self):
        if not self._visible:
            self.hide()
            # Принудительно обновляем родителя (убирает «призрак»)
            if self.host:
                self.host.update()

    def toggle(self):
        if self._visible:
            self.hide_spotlight()
        else:
            self.show_spotlight()

    def _reposition(self):
        x = (self.host.width() - self.width()) // 2
        y = int(self.host.height() * 0.18)
        self.move(max(20, x), max(40, y))

    def resizeEvent(self, e):
        self._reposition()
        super().resizeEvent(e)

    # ------------------------------------------------------------
    #  Поиск
    # ------------------------------------------------------------

    def _actions(self):
        return [
            ("action_open", "settings", "Открыть Настройки", "settings"),
            ("action_open", "files",    "Открыть Проводник", "files"),
            ("action_open", "terminal", "Открыть Терминал",  "terminal"),
            ("action_open", "notes",    "Открыть Заметки",   "editor"),
            ("action_open", "clock",    "Открыть Часы",      "clock"),
            ("action_open", "calendar", "Открыть Календарь", "calendar"),
            ("action_open", "gallery",  "Открыть Галерею",   "gallery"),
            ("action_open", "music",    "Открыть Музыку",    "music"),
            ("action_open", "weather",  "Открыть Погоду",    "cloud"),
            ("action_open", "browser",  "Открыть Браузер",   "browser"),
            ("action_close_all", "",    "Закрыть все окна",  "close"),
            ("action_hide_dock", "",    "Скрыть / показать док", "grid"),
            ("action_install",   "",    "Установить приложение (.py)", "download"),
        ]

    def _collect_files(self, limit=200):
        d = self._get_desktop()
        if d is None or not hasattr(d, "vfs"):
            return []
        vfs = d.vfs
        result = []

        def walk(path, depth=0):
            if len(result) >= limit or depth > 6:
                return
            try:
                items = vfs.listdir(path)
            except Exception:
                return
            for it in items:
                if len(result) >= limit:
                    return
                result.append({
                    "name": it["name"],
                    "path": it["path"],
                    "is_dir": it["is_dir"],
                })
                if it["is_dir"] and it["name"] not in (".", ".."):
                    walk(it["path"], depth + 1)

        try:
            walk("/")
        except Exception:
            pass
        return result

    def _get_desktop(self):
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

    def _update_results(self, query: str):
        q = (query or "").strip().lower()

        apps_items = []
        if self._registry:
            for app_id, info in self._registry.apps.items():
                if not q or q in info.name.lower() or q in app_id.lower():
                    apps_items.append(("app", app_id, info.name, info.app_id))

        files_items = []
        if q:
            for f in self._collect_files(limit=300):
                if q in f["name"].lower():
                    files_items.append(("file", f["path"], f["name"], "files"))

        actions_items = []
        for kind, payload, label, icon_name in self._actions():
            if not q or q in label.lower():
                actions_items.append((kind, payload, label, icon_name))

        if q:
            combined = apps_items + files_items[:20] + actions_items[:5]
        else:
            combined = actions_items + apps_items[:20]

        self._results = combined

        self.listw.clear()
        for kind, payload, label, icon_name in combined:
            if kind == "app":
                prefix = ""
            elif kind == "file":
                prefix = "Файл:  "
            elif kind.startswith("action"):
                prefix = "Действие:  "
            else:
                prefix = ""

            item = QListWidgetItem(prefix + label)
            item.setIcon(QIcon(get_icon(icon_name, 20, state().get("accent"))))
            item.setSizeHint(QSize(0, 40))
            item.setData(Qt.UserRole, (kind, payload))
            self.listw.addItem(item)

        if self.listw.count() > 0:
            self.listw.setCurrentRow(0)

    # ------------------------------------------------------------
    #  Активация
    # ------------------------------------------------------------

    def _activate_current(self):
        item = self.listw.currentItem()
        if item is None:
            return
        kind, payload = item.data(Qt.UserRole)

        if kind == "app":
            self.hide_spotlight()
            self.app_launch_requested.emit(payload)
        elif kind == "file":
            self.hide_spotlight()
            self.file_open_requested.emit(payload)
        elif kind == "action_open":
            self.hide_spotlight()
            self.app_launch_requested.emit(payload)
        elif kind == "action_close_all":
            self.hide_spotlight()
            self.action_requested.emit("close_all")
        elif kind == "action_hide_dock":
            self.hide_spotlight()
            self.action_requested.emit("toggle_dock")
        elif kind == "action_install":
            self.hide_spotlight()
            self.action_requested.emit("install_app")

    # ------------------------------------------------------------
    #  Клавиши
    # ------------------------------------------------------------

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.hide_spotlight()
            e.accept()
            return
        if e.key() in (Qt.Key_Up, Qt.Key_Down):
            row = self.listw.currentRow()
            n = self.listw.count()
            if n == 0:
                return
            if e.key() == Qt.Key_Up:
                row = (row - 1) % n
            else:
                row = (row + 1) % n
            self.listw.setCurrentRow(row)
            e.accept()
            return
        super().keyPressEvent(e)