from PySide6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QListWidget,
                                QListWidgetItem, QTextEdit, QPushButton,
                                QInputDialog, QMessageBox, QLabel)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon

from ui.icons import get_icon
from ui.settings_state import state
from ui.context_menu import make_menu

APP_NAME = "Заметки"
APP_ICON = "notes"
APP_VERSION = "0.3"
APP_AUTHOR = "MountOS"


def _get_vfs(widget):
    p = widget
    while p is not None:
        if hasattr(p, "vfs"):
            return p.vfs
        p = p.parent()
    return None


def _get_desktop(widget):
    p = widget
    while p is not None:
        if hasattr(p, "notifications"):
            return p
        p = p.parent()
    return None


def build():
    root = QWidget()
    h = QHBoxLayout(root)
    h.setContentsMargins(0, 0, 0, 0)
    h.setSpacing(0)

    # ---- Список заметок ----
    left = QWidget()
    left.setFixedWidth(220)
    left.setStyleSheet("""
        background: rgba(255,255,255,0.04);
        border-right: 1px solid rgba(255,255,255,0.08);
    """)
    ll = QVBoxLayout(left)
    ll.setContentsMargins(12, 14, 12, 14)
    ll.setSpacing(8)

    title = QLabel("Заметки")
    title.setStyleSheet("color: white; font-size: 14px; font-weight: 600; padding: 2px 4px;")
    ll.addWidget(title)

    add_btn = QPushButton("＋  Новая заметка")
    add_btn.setCursor(Qt.PointingHandCursor)
    add_btn.setStyleSheet("""
        QPushButton {
            background: rgba(110,198,255,0.18);
            color: white;
            border: 1px solid rgba(110,198,255,0.55);
            border-radius: 10px;
            padding: 8px 10px;
            text-align: left;
            font-size: 12px;
        }
        QPushButton:hover { background: rgba(110,198,255,0.35); }
    """)
    ll.addWidget(add_btn)

    listing = QListWidget()
    listing.setStyleSheet("""
        QListWidget {
            background: transparent;
            border: none;
            color: white;
            outline: none;
            font-size: 12px;
        }
        QListWidget::item {
            padding: 8px 10px;
            border-radius: 8px;
        }
        QListWidget::item:hover { background: rgba(255,255,255,0.08); }
        QListWidget::item:selected { background: rgba(110,198,255,0.30); }
    """)
    ll.addWidget(listing, 1)

    h.addWidget(left)

    # ---- Редактор ----
    right = QWidget()
    rl = QVBoxLayout(right)
    rl.setContentsMargins(18, 16, 18, 18)
    rl.setSpacing(10)

    name_edit = QLabel("Выберите заметку")
    name_edit.setStyleSheet("color: white; font-size: 14px; font-weight: 600;")
    rl.addWidget(name_edit)

    editor = QTextEdit()
    editor.setPlaceholderText("Текст заметки…")
    editor.setStyleSheet("""
        QTextEdit {
            background: rgba(0,0,0,0.22);
            color: white;
            border: 1px solid rgba(255,255,255,0.10);
            border-radius: 12px;
            padding: 14px;
            font-size: 13px;
            font-family: 'Segoe UI', sans-serif;
        }
    """)
    rl.addWidget(editor, 1)

    status = QLabel("")
    status.setStyleSheet("color: rgba(255,255,255,0.45); font-size: 11px;")
    rl.addWidget(status)

    h.addWidget(right, 1)

    # ---- Логика ----
    current = {"path": None}
    autosave = QTimer(root)
    autosave.setInterval(900)
    autosave.setSingleShot(True)

    def load_notes():
        vfs = _get_vfs(root)
        if vfs is None:
            return
        listing.clear()
        vfs.mkdir("/Notes")
        for f in vfs.listdir("/Notes"):
            if f["is_dir"] or not f["name"].endswith(".txt"):
                continue
            item = QListWidgetItem(QIcon(get_icon("notes", 16, state().get("accent"))),
                                   f["name"][:-4])
            item.setData(Qt.UserRole, f["path"])
            listing.addItem(item)

    def open_note(item):
        vfs = _get_vfs(root)
        path = item.data(Qt.UserRole)
        current["path"] = path
        name_edit.setText(vfs.basename(path)[:-4])
        editor.setPlainText(vfs.read_text(path, ""))
        status.setText(f"Открыт: {path}")

    def save_now():
        vfs = _get_vfs(root)
        if not current["path"] or vfs is None:
            return
        vfs.write_text(current["path"], editor.toPlainText())
        status.setText("Сохранено ✓")

    def on_change():
        status.setText("Изменено…")
        autosave.start()

    autosave.timeout.connect(save_now)
    editor.textChanged.connect(on_change)
    listing.itemClicked.connect(open_note)

    def new_note():
        vfs = _get_vfs(root)
        name, ok = QInputDialog.getText(root, "Новая заметка", "Название:")
        if not ok or not name.strip():
            return
        safe = "".join(c for c in name.strip() if c not in r'\/:*?"<>|')
        if not safe:
            return
        path = f"/Notes/{safe}.txt"
        vfs.write_text(path, "")
        load_notes()
        # Выделяем новую
        for i in range(listing.count()):
            if listing.item(i).data(Qt.UserRole) == path:
                listing.setCurrentItem(listing.item(i))
                open_note(listing.item(i))
                break

    add_btn.clicked.connect(new_note)

    def context_menu(pos):
        item = listing.itemAt(pos)
        if not item:
            return
        vfs = _get_vfs(root)
        path = item.data(Qt.UserRole)
        menu = make_menu(listing)

        a_ren = menu.addAction("Переименовать")
        def do_ren():
            new, ok = QInputDialog.getText(root, "Переименовать", "Новое имя:",
                                            text=vfs.basename(path)[:-4])
            if ok and new.strip():
                dst = f"/Notes/{new.strip()}.txt"
                vfs.rename(path, dst)
                load_notes()
        a_ren.triggered.connect(do_ren)

        a_del = menu.addAction("Удалить")
        def do_del():
            ok = QMessageBox.question(root, "Удалить",
                f"Удалить «{vfs.basename(path)[:-4]}»?",
                QMessageBox.Yes | QMessageBox.No)
            if ok == QMessageBox.Yes:
                vfs.delete(path)
                if current["path"] == path:
                    current["path"] = None
                    editor.clear()
                    name_edit.setText("Выберите заметку")
                load_notes()
        a_del.triggered.connect(do_del)

        menu.addSeparator()
        a_save = menu.addAction("Сохранить сейчас")
        a_save.triggered.connect(save_now)

        menu.exec(listing.mapToGlobal(pos))

    listing.setContextMenuPolicy(Qt.CustomContextMenu)
    listing.customContextMenuRequested.connect(context_menu)

    load_notes()

    # Авто-открытие первой
    if listing.count() > 0:
        listing.setCurrentRow(0)
        open_note(listing.item(0))

    return root