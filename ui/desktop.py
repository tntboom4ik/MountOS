"""
MountOS — Рабочий стол.
Центральный модуль, который собирает всё вместе.
"""
import os
import json
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QLabel, QFileDialog,
                                QApplication, QMessageBox)
from PySide6.QtCore import Qt, QTimer, QTime, QPropertyAnimation
from PySide6.QtGui import QPainter, QLinearGradient, QColor, QBrush

from ui.panel import TopPanel
from ui.dock import Dock
from ui.taskbar import Taskbar
from ui.glass_window import GlassWindow
from ui.notifications import NotificationCenter
from ui.settings_state import state
from ui.widgets import WIDGET_FACTORY, WIDGET_NAMES
from ui.shortcuts import Shortcut
from ui.desktop_menu import show_desktop_menu
from ui.app_menu import AppMenu
from ui.notif_center import NotificationCenterPanel
from ui.spotlight import Spotlight
from ui.hotkeys import HotkeyManager
from apps.settings import WALLPAPERS

from system.registry import Registry
from system.vfs import VFS
from system import paths
from system.i18n import tr, on_change


class Desktop(QWidget):
    def __init__(self, base_dir):
        super().__init__()
        self.base_dir = base_dir
        self.setWindowTitle("MountOS")
        self.setContextMenuPolicy(Qt.DefaultContextMenu)

        # Оптимизация рендеринга (фикс «призраков»)
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)
        self.setAutoFillBackground(False)

        # ---- VFS ----
        self.vfs = VFS(base_dir)
        self.vfs.ensure_default_structure()

        # ---- UI ----
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.panel = TopPanel(self)
        self.panel.setObjectName("TopPanel")
        root.addWidget(self.panel)
        root.addStretch(1)

        self.taskbar = Taskbar(self)
        self.taskbar_wrap = QWidget(self)
        tw = QVBoxLayout(self.taskbar_wrap)
        tw.setContentsMargins(0, 0, 0, 8)
        tw.addWidget(self.taskbar, alignment=Qt.AlignHCenter)
        root.addWidget(self.taskbar_wrap, alignment=Qt.AlignHCenter)

        # Док
        self.dock = Dock(self)
        self.dock.app_launch_requested.connect(self.open_app)
        self.dock.app_install_requested.connect(self.install_app)
        self.dock.app_delete_requested.connect(self.uninstall_app)
        self.dock.height_changed.connect(self._save_dock_height)
        root.addWidget(self.dock, alignment=Qt.AlignHCenter)

        self.welcome = QLabel(tr("app.welcome"))
        self.welcome.setAlignment(Qt.AlignCenter)
        self.welcome.setStyleSheet("""
            color: rgba(255,255,255,0.55);
            font-size: 26px;
            font-weight: 200;
            letter-spacing: 3px;
        """)
        root.insertWidget(1, self.welcome)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(1000)
        self._tick()

        # Реестр
        self.registry = Registry(base_dir)
        self.dock.populate(self.registry.apps)

        # Уведомления
        self.notifications = NotificationCenter(self)
        if state().get("show_startup_notification", True):
            QTimer.singleShot(600, lambda: self.notifications.push(
                tr("notif.mountos"),
                tr("notif.loaded_apps", n=len(self.registry.apps))))

        self.windows = []
        self._cascade = 0

        self.widgets = []
        self.shortcuts = []

        # Меню приложений
        self.app_menu = AppMenu(self)
        self.app_menu.set_registry(self.registry)
        self.app_menu.app_launch_requested.connect(self.open_app)
        self.app_menu.app_delete_requested.connect(self.uninstall_app)

        # Центр уведомлений
        self.notif_center = NotificationCenterPanel(self)

        # Spotlight
        self.spotlight = Spotlight(self)
        self.spotlight.set_registry(self.registry)
        self.spotlight.app_launch_requested.connect(self.open_app)
        self.spotlight.file_open_requested.connect(self.open_file)
        self.spotlight.action_requested.connect(self._spotlight_action)

        # Защита от двойного Spotlight
        all_spots = [c for c in self.findChildren(object)
                     if c.__class__.__name__ == "Spotlight"]
        if len(all_spots) > 1:
            print(f"[MountOS] найдено {len(all_spots)} Spotlight, удаляю лишние")
            for extra in all_spots:
                if extra is not self.spotlight:
                    extra.setParent(None)
                    extra.deleteLater()
        self.spotlight.hide()

        # Горячие клавиши
        self.hotkeys = HotkeyManager(self)

        # Реакции
        state().changed.connect(self._on_state)
        on_change(self._on_language)
        self._apply_visibility()

        QTimer.singleShot(150, self._apply_dock_height)
        QTimer.singleShot(200, self._load_desktop)

    # ------------------------------------------------------------------
    def _on_state(self, key, value):
        if key == "wallpaper":
            self.update()
        elif key in ("show_dock", "show_welcome"):
            self._apply_visibility()
        elif key == "accent":
            self.update()
        elif key == "dock_height":
            self._apply_dock_height()

    def _on_language(self, lang):
        self.welcome.setText(tr("app.welcome"))
        self.setWindowTitle(tr("app.name"))

    def _apply_visibility(self):
        self.dock.setVisible(state().get("show_dock", True))
        self.welcome.setVisible(state().get("show_welcome", True))

    def _tick(self):
        self.panel.set_time(QTime.currentTime().toString("HH:mm"))

    # ------------------------------------------------------------------
    def _save_dock_height(self, h: int):
        state().set("dock_height", h)

    def _apply_dock_height(self):
        try:
            from PySide6.QtCore import QSize as QSz
            h = state().get("dock_height", 90)
            if h and 90 <= h <= 160:
                self.dock.setFixedHeight(h)
                ratio = (h - 90) / 70
                size = int(52 + ratio * 30)
                self.dock._icon_size = size
                for ic in self.dock._icons.values():
                    ic.base_size = size
                    ic.setFixedSize(size, size)
                    ic.setIconSize(QSz(int(size * 0.6), int(size * 0.6)))
        except Exception as e:
            print(f"[Desktop] dock height: {e}")

    # ------------------------------------------------------------------
    def _spotlight_action(self, name: str):
        if name == "close_all":
            for w in list(self.windows):
                w.close()
        elif name == "toggle_dock":
            state().set("show_dock", not state().get("show_dock"))
        elif name == "install_app":
            self.install_app()

    # ------------------------------------------------------------------
    def _save_desktop(self):
        data = {
            "widgets": [
                {"id": w.widget_id, "x": w.x(), "y": w.y()}
                for w in self.widgets
            ],
            "shortcuts": [
                {"target_id": s.target_id, "target_type": s.target_type,
                 "label": s.label_text, "icon": s.icon_name,
                 "x": s.x(), "y": s.y()}
                for s in self.shortcuts
            ],
        }
        try:
            paths.DESKTOP_JSON.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8")
        except Exception as e:
            print("[MountOS] ошибка сохранения рабочего стола:", e)

    def _load_desktop(self):
        if not paths.DESKTOP_JSON.exists():
            self.add_widget("clock", x=80,  y=90)
            self.add_widget("system", x=80, y=260)
            self.add_widget("sticky", x=350, y=90)
            self.add_widget("quick",  x=350, y=280)
            return

        try:
            data = json.loads(paths.DESKTOP_JSON.read_text(encoding="utf-8"))
        except Exception:
            return

        for w in data.get("widgets", []):
            self.add_widget(w["id"], x=w.get("x", 100), y=w.get("y", 100))

        for s in data.get("shortcuts", []):
            if s["target_type"] == "app" and s["target_id"] not in self.registry.apps:
                continue
            if s["target_type"] == "file" and not self.vfs.exists(s["target_id"]):
                continue
            self.add_shortcut(s["target_id"], s["target_type"], s["label"],
                              s["icon"], x=s.get("x", 100), y=s.get("y", 100))

    # ------------------------------------------------------------------
    def add_widget(self, widget_id: str, x=None, y=None):
        factory = WIDGET_FACTORY.get(widget_id)
        if not factory:
            return
        w = factory(self)
        if x is None:
            x = 80 + (len(self.widgets) % 4) * 30
        if y is None:
            y = 100 + (len(self.widgets) % 4) * 30
        w.move(x, y)
        w.remove_requested.connect(self._remove_widget)
        w.position_changed.connect(lambda *_: self._save_desktop())
        w.show()
        self.widgets.append(w)
        self._save_desktop()
        return w

    def _remove_widget(self, w):
        if w in self.widgets:
            self.widgets.remove(w)
        w.setParent(None)
        self._save_desktop()

    # ------------------------------------------------------------------
    def add_app_shortcut(self, app_id: str, x=None, y=None):
        info = self.registry.get(app_id)
        if not info:
            return
        return self.add_shortcut(app_id, "app", info.name, info.app_id, x, y)

    def add_file_shortcut(self, path: str, label: str, x=None, y=None):
        return self.add_shortcut(path, "file", label, "files", x, y)

    def add_shortcut(self, target_id, target_type, label, icon_name,
                     x=None, y=None):
        if x is None:
            x = 40 + (len(self.shortcuts) % 8) * 20
        if y is None:
            y = 480 + (len(self.shortcuts) % 4) * 20
        s = Shortcut(self, target_id, target_type, label, icon_name, x, y)
        s.activated.connect(self._open_shortcut)
        s.remove_requested.connect(self._remove_shortcut)
        s.position_changed.connect(lambda *_: self._save_desktop())
        s.show()
        s.raise_()
        self.shortcuts.append(s)
        self._save_desktop()
        return s

    def _open_shortcut(self, shortcut):
        if shortcut.target_type == "app":
            if shortcut.target_id not in self.registry.apps:
                self.notifications.push(tr("common.error"),
                                        f"«{shortcut.label_text}»")
                self._remove_shortcut(shortcut)
                return
            self.open_app(shortcut.target_id)
        elif shortcut.target_type == "file":
            if not self.vfs.exists(shortcut.target_id):
                self.notifications.push(tr("common.error"), shortcut.target_id)
                self._remove_shortcut(shortcut)
                return
            self.open_file(shortcut.target_id)

    def _remove_shortcut(self, shortcut):
        if shortcut in self.shortcuts:
            self.shortcuts.remove(shortcut)
        shortcut.setParent(None)
        self._save_desktop()

    # ------------------------------------------------------------------
    def contextMenuEvent(self, e):
        child = self.childAt(e.pos())
        if child and (isinstance(child, Shortcut) or
                      any(child is w or w.isAncestorOf(child) for w in self.widgets)):
            return
        show_desktop_menu(self, e.globalPos())

    # ------------------------------------------------------------------
    def open_app(self, app_id: str):
        info = self.registry.get(app_id)
        if not info:
            self.notifications.push(tr("common.error"), app_id)
            return
        try:
            content = info.build_fn()
        except Exception as e:
            import traceback; traceback.print_exc()
            self.notifications.push(tr("common.error"), f"{info.name}: {e}")
            return

        win = GlassWindow(self, info.name, content,
                          width=860, height=560,
                          app_id=info.app_id, icon=info.app_id)
        win.closed.connect(self._on_window_closed)

        offset = (self._cascade % 6) * 30
        self._cascade += 1
        win.move(180 + offset, 90 + offset)

        win.show()
        win.raise_()
        win.activateWindow()

        anim = QPropertyAnimation(win, b"windowOpacity")
        anim.setDuration(220)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.start()
        win._anim = anim

        self.windows.append(win)
        self.dock.mark_active(app_id, True)
        self.taskbar.add_window(win, info.app_id, info.name)

    def open_file(self, vpath: str):
        if not self.vfs.exists(vpath):
            self.notifications.push(tr("common.error"), vpath)
            return
        if self.vfs.is_dir(vpath):
            self.open_app("files")
            return

        from PySide6.QtWidgets import QTextEdit
        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setContentsMargins(16, 12, 16, 16)
        edit = QTextEdit()
        try:
            edit.setText(self.vfs.read_text(vpath))
        except Exception:
            edit.setText("[binary]")
        edit.setStyleSheet("""
            QTextEdit {
                background: rgba(0,0,0,0.25);
                color: white;
                border: 1px solid rgba(255,255,255,0.10);
                border-radius: 12px;
                padding: 12px;
                font-family: Consolas, monospace;
                font-size: 13px;
            }
        """)
        lay.addWidget(edit)

        win = GlassWindow(self, self.vfs.basename(vpath), content,
                          width=700, height=500,
                          app_id="__viewer__", icon="files")
        win.closed.connect(self._on_window_closed)
        win.move(240, 120)
        win.show()
        win.raise_()
        win.activateWindow()
        self.windows.append(win)

    def _on_window_closed(self, win):
        if win in self.windows:
            self.windows.remove(win)
        app_id = getattr(win, "app_id", None)
        if app_id and app_id != "__viewer__":
            still = any(getattr(w, "app_id", None) == app_id for w in self.windows)
            self.dock.mark_active(app_id, still)
        self.taskbar.remove_window(win)

    # ------------------------------------------------------------------
    def install_app(self):
        path, _ = QFileDialog.getOpenFileName(
            self, tr("settings.apps.install_title"), "", "Python (*.py)")
        if not path:
            return
        info, err = self.registry.install(path)
        if err:
            self.notifications.push(tr("common.error"), err)
            return
        self.dock.populate(self.registry.apps)
        self.notifications.push(tr("notif.app_installed"),
                                f"{info.name} v{info.version}")
        if self.app_menu:
            self.app_menu.set_registry(self.registry)

    def uninstall_app(self, app_id: str):
        info = self.registry.get(app_id)
        if not info:
            self.notifications.push(tr("common.error"), app_id)
            return
        if info.builtin:
            self.notifications.push(tr("dock.cannot_delete_builtin"), info.name)
            return

        ans = QMessageBox.question(
            self, tr("settings.apps.delete_title"),
            tr("settings.apps.delete_q", name=info.name),
            QMessageBox.Yes | QMessageBox.No)
        if ans != QMessageBox.Yes:
            return

        for w in list(self.windows):
            if getattr(w, "app_id", None) == app_id:
                w.close()

        self.registry.remove(app_id)
        self.dock.populate(self.registry.apps)
        self.notifications.push(tr("notif.app_removed"), info.name)
        if self.app_menu:
            self.app_menu.set_registry(self.registry)

    # ------------------------------------------------------------------
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        # Очищаем фон полностью (защита от «призраков»)
        p.fillRect(self.rect(), QColor("#0A0E1A"))

        colors, g1, g2 = WALLPAPERS.get(
            state().get("wallpaper", "cosmic"),
            WALLPAPERS["cosmic"])

        grad = QLinearGradient(0, 0, self.width(), self.height())
        grad.setColorAt(0.0, QColor(colors[0]))
        grad.setColorAt(0.5, QColor(colors[1]))
        grad.setColorAt(1.0, QColor(colors[2]))
        p.fillRect(self.rect(), QBrush(grad))

        glow1 = QLinearGradient(0, 0, 600, 600)
        glow1.setColorAt(0, QColor(*g1, 40))
        glow1.setColorAt(1, QColor(*g1, 0))
        p.setBrush(QBrush(glow1))
        p.setPen(Qt.NoPen)
        p.drawEllipse(-200, -200, 900, 900)

        glow2 = QLinearGradient(self.width(), self.height(),
                                self.width() - 700, self.height() - 700)
        glow2.setColorAt(0, QColor(*g2, 35))
        glow2.setColorAt(1, QColor(*g2, 0))
        p.setBrush(QBrush(glow2))
        p.drawEllipse(self.width() - 500, self.height() - 500, 1000, 1000)

    def closeEvent(self, e):
        self._save_desktop()
        super().closeEvent(e)