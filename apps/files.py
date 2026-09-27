from PySide6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QLabel,
                                QPushButton, QLineEdit, QListWidget, QListWidgetItem,
                                QInputDialog, QMessageBox, QFileDialog)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon

from ui.icons import get_icon
from ui.settings_state import state
from ui.context_menu import make_menu

APP_NAME = "Проводник"
APP_ICON = "files"
APP_VERSION = "0.4"
APP_AUTHOR = "MountOS"


# ---------------- Поиск VFS и Desktop ----------------

def _get_vfs(widget):
    p = widget
    while p is not None:
        if hasattr(p, "vfs"):
            return p.vfs
        if hasattr(p, "desktop_ref") and p.desktop_ref is not None:
            return getattr(p.desktop_ref, "vfs", None)
        p = p.parent()
    return None


def _get_desktop(widget):
    p = widget
    while p is not None:
        if hasattr(p, "notifications") and hasattr(p, "open_app"):
            return p
        if hasattr(p, "desktop_ref") and p.desktop_ref is not None:
            return p.desktop_ref
        p = p.parent()
    return None


def _human_size(n):
    for unit in ("Б", "КБ", "МБ", "ГБ"):
        if n < 1024:
            return f"{n:.0f} {unit}"
        n /= 1024
    return f"{n:.1f} ТБ"


def _icon_btn_style():
    return """
        QPushButton {
            background: rgba(255,255,255,0.08);
            color: white;
            border: 1px solid rgba(255,255,255,0.14);
            border-radius: 10px;
            font-size: 14px;
        }
        QPushButton:hover { background: rgba(255,255,255,0.20); }
        QPushButton:pressed { background: rgba(110,198,255,0.35); }
    """


def build():
    root = QWidget()
    h = QHBoxLayout(root)
    h.setContentsMargins(0, 0, 0, 0)
    h.setSpacing(0)

    # ---------------- Сайдбар ----------------
    side = QWidget()
    side.setFixedWidth(180)
    side.setStyleSheet("""
        background: rgba(255,255,255,0.04);
        border-right: 1px solid rgba(255,255,255,0.08);
    """)
    sl = QVBoxLayout(side)
    sl.setContentsMargins(12, 14, 12, 14)
    sl.setSpacing(2)

    PLACES = [
        ("Главная",     "/"),
        ("Документы",   "/Documents"),
        ("Изображения", "/Pictures"),
        ("Заметки",     "/Notes"),
        ("Загрузки",    "/Downloads"),
    ]

    for name, _ in PLACES:
        b = QPushButton(name)
        b.setCursor(Qt.PointingHandCursor)
        b.setFixedHeight(34)
        b.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: rgba(255,255,255,0.78);
                border: none;
                border-radius: 8px;
                padding: 6px 10px;
                text-align: left;
                font-size: 12px;
            }
            QPushButton:hover { background: rgba(255,255,255,0.08); color: white; }
        """)
        sl.addWidget(b)

    sl.addStretch(1)

    # ---------------- Основная область ----------------
    main = QWidget()
    ml = QVBoxLayout(main)
    ml.setContentsMargins(16, 14, 16, 16)
    ml.setSpacing(10)

    # Навигация
    nav = QHBoxLayout()
    nav.setSpacing(8)

    btn_back = QPushButton()
    btn_back.setIcon(QIcon(get_icon("back", 18, "#FFFFFF")))
    btn_back.setIconSize(QSize(16, 16))
    btn_back.setFixedSize(34, 34)
    btn_back.setCursor(Qt.PointingHandCursor)
    btn_back.setStyleSheet(_icon_btn_style())

    btn_up = QPushButton("↑")
    btn_up.setFixedSize(34, 34)
    btn_up.setCursor(Qt.PointingHandCursor)
    btn_up.setStyleSheet(_icon_btn_style())

    btn_refresh = QPushButton("⟳")
    btn_refresh.setFixedSize(34, 34)
    btn_refresh.setCursor(Qt.PointingHandCursor)
    btn_refresh.setStyleSheet(_icon_btn_style())

    path_edit = QLineEdit("/")
    path_edit.setStyleSheet("""
        QLineEdit {
            background: rgba(255,255,255,0.08);
            color: white;
            border: 1px solid rgba(255,255,255,0.15);
            border-radius: 10px;
            padding: 7px 12px;
            font-family: Consolas, monospace;
            font-size: 12px;
        }
        QLineEdit:focus { border: 1px solid rgba(110,198,255,0.60); }
    """)

    nav.addWidget(btn_back)
    nav.addWidget(btn_up)
    nav.addWidget(btn_refresh)
    nav.addWidget(path_edit, 1)
    ml.addLayout(nav)

    # Список файлов
    listing = QListWidget()
    listing.setStyleSheet("""
        QListWidget {
            background: rgba(0,0,0,0.18);
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 12px;
            padding: 6px;
            color: white;
            font-size: 13px;
            outline: none;
        }
        QListWidget::item {
            padding: 8px 10px;
            border-radius: 8px;
        }
        QListWidget::item:hover { background: rgba(255,255,255,0.08); }
        QListWidget::item:selected { background: rgba(110,198,255,0.30); }
    """)
    listing.setIconSize(QSize(20, 20))
    ml.addWidget(listing, 1)

    h.addWidget(side)
    h.addWidget(main, 1)

    # ---------------- Логика ----------------
    st = {"cwd": "/", "history": [], "future": [], "clip": None}

    def navigate(path, add_history=True):
        vfs = _get_vfs(root)
        if vfs is None:
            return
        if not vfs.exists(path) or not vfs.is_dir(path):
            return
        if add_history:
            st["history"].append(st["cwd"])
            st["future"].clear()
        st["cwd"] = path
        path_edit.setText(path)
        refresh()

    def refresh():
        vfs = _get_vfs(root)
        listing.clear()
        if vfs is None:
            item = QListWidgetItem("⚠  Не удалось получить доступ к файловой системе")
            item.setForeground(Qt.red)
            listing.addItem(item)
            return
        items = vfs.listdir(st["cwd"])
        if not items:
            item = QListWidgetItem("   (пусто — создай файл правым кликом)")
            item.setForeground(Qt.gray)
            listing.addItem(item)
            return
        for it in items:
            icon_name = "files"
            icon = QIcon(get_icon(icon_name, 20, state().get("accent")))
            size_txt = "" if it["is_dir"] else f"   {_human_size(it['size'])}"
            prefix = "📁  " if it["is_dir"] else "📄  "
            item = QListWidgetItem(icon, prefix + it["name"] + size_txt)
            item.setData(Qt.UserRole, it)
            listing.addItem(item)

    def open_item(item):
        data = item.data(Qt.UserRole)
        if not data:
            return
        if data["is_dir"]:
            navigate(data["path"])
        else:
            d = _get_desktop(root)
            if d:
                d.open_file(data["path"])

    listing.itemDoubleClicked.connect(open_item)
    path_edit.returnPressed.connect(lambda: navigate(path_edit.text().strip()))

    def go_back():
        if st["history"]:
            st["future"].append(st["cwd"])
            prev = st["history"].pop()
            navigate(prev, add_history=False)

    def go_up():
        vfs = _get_vfs(root)
        if vfs:
            navigate(vfs.parent(st["cwd"]))

    btn_back.clicked.connect(go_back)
    btn_up.clicked.connect(go_up)
    btn_refresh.clicked.connect(refresh)

    # ---------------- Правый клик ----------------
    def context_menu(pos):
        item = listing.itemAt(pos)
        menu = make_menu(listing)

        if item and item.data(Qt.UserRole):
            data = item.data(Qt.UserRole)
            a_open = menu.addAction("Открыть")
            a_open.triggered.connect(lambda: open_item(item))

            if not data["is_dir"]:
                a_edit = menu.addAction("Редактировать текст")
                a_edit.triggered.connect(lambda: _edit_text(root, data["path"]))

            menu.addSeparator()

            a_ren = menu.addAction("Переименовать")
            a_ren.triggered.connect(lambda: _rename(root, data["path"], refresh))

            a_cp = menu.addAction("Копировать")
            a_cp.triggered.connect(lambda: st.update({"clip": data["path"]}))

            if st.get("clip"):
                a_pst = menu.addAction("Вставить")
                a_pst.triggered.connect(lambda: _paste(root, st, refresh))

            menu.addSeparator()

            a_del = menu.addAction("Удалить")
            a_del.triggered.connect(lambda: _delete(root, data["path"], refresh))
        else:
            a_newf = menu.addAction("📄 Новый файл")
            a_newf.triggered.connect(lambda: _new_file(root, st["cwd"], refresh))
            a_newd = menu.addAction("📁 Новая папка")
            a_newd.triggered.connect(lambda: _new_folder(root, st["cwd"], refresh))
            menu.addSeparator()
            a_imp = menu.addAction("⬆ Импортировать файл с ПК")
            a_imp.triggered.connect(lambda: _import_real(root, st["cwd"], refresh))
            menu.addSeparator()
            a_ref = menu.addAction("⟳ Обновить")
            a_ref.triggered.connect(refresh)

        menu.exec(listing.mapToGlobal(pos))

    listing.setContextMenuPolicy(Qt.CustomContextMenu)
    listing.customContextMenuRequested.connect(context_menu)

    # Кнопки сайдбара
    for b, (_, path) in zip(side.findChildren(QPushButton), PLACES):
        b.clicked.connect(lambda _, p=path: navigate(p))

    navigate("/")
    return root


# ---------------- Хелперы ----------------

def _new_file(root, cwd, refresh):
    vfs = _get_vfs(root)
    if vfs is None:
        return
    name, ok = QInputDialog.getText(root, "Новый файл", "Имя:", text="файл.txt")
    if not ok or not name.strip():
        return
    vfs.write_text(vfs.join(cwd, name.strip()), "")
    refresh()


def _new_folder(root, cwd, refresh):
    vfs = _get_vfs(root)
    if vfs is None:
        return
    name, ok = QInputDialog.getText(root, "Новая папка", "Имя:", text="Папка")
    if not ok or not name.strip():
        return
    vfs.mkdir(vfs.join(cwd, name.strip()))
    refresh()


def _rename(root, path, refresh):
    vfs = _get_vfs(root)
    if vfs is None:
        return
    old_name = vfs.basename(path)
    name, ok = QInputDialog.getText(root, "Переименовать", "Новое имя:", text=old_name)
    if not ok or not name.strip() or name.strip() == old_name:
        return
    new_path = vfs.join(vfs.parent(path), name.strip())
    vfs.rename(path, new_path)
    refresh()


def _delete(root, path, refresh):
    vfs = _get_vfs(root)
    if vfs is None:
        return
    name = vfs.basename(path)
    ok = QMessageBox.question(root, "Удаление",
        f"Удалить «{name}»?", QMessageBox.Yes | QMessageBox.No)
    if ok == QMessageBox.Yes:
        vfs.delete(path)
        refresh()


def _paste(root, st, refresh):
    vfs = _get_vfs(root)
    if vfs is None:
        return
    src = st.get("clip")
    if not src or not vfs.exists(src):
        return
    name = vfs.basename(src)
    dst = vfs.join(st["cwd"], name)
    n = 1
    base, dot, ext = name.partition(".")
    while vfs.exists(dst):
        dst = vfs.join(st["cwd"], f"{base}_{n}{dot}{ext}")
        n += 1
    vfs.copy(src, dst)
    refresh()


def _edit_text(root, path):
    vfs = _get_vfs(root)
    if vfs is None:
        return
    from PySide6.QtWidgets import QDialog, QVBoxLayout as VL, QTextEdit, QDialogButtonBox
    dlg = QDialog(root)
    dlg.setWindowTitle(f"Редактор: {vfs.basename(path)}")
    dlg.resize(640, 480)
    dlg.setStyleSheet("""
        QDialog { background: #1A1F35; }
        QTextEdit {
            background: rgba(0,0,0,0.30);
            color: white;
            border: 1px solid rgba(255,255,255,0.15);
            border-radius: 10px;
            padding: 10px;
            font-family: Consolas, monospace;
            font-size: 13px;
        }
    """)
    lay = VL(dlg)
    edit = QTextEdit()
    edit.setText(vfs.read_text(path, ""))
    lay.addWidget(edit)
    bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
    bb.accepted.connect(dlg.accept)
    bb.rejected.connect(dlg.reject)
    lay.addWidget(bb)
    if dlg.exec() == QDialog.Accepted:
        vfs.write_text(path, edit.toPlainText())
        d = _get_desktop(root)
        if d:
            d.notifications.push("Файл сохранён", vfs.basename(path))


def _import_real(root, cwd, refresh):
    """Импорт реального файла с диска в песочницу MountOS."""
    import os
    import shutil
    vfs = _get_vfs(root)
    if vfs is None:
        QMessageBox.warning(root, "Ошибка", "Файловая система недоступна")
        return
    path, _ = QFileDialog.getOpenFileName(root, "Импортировать файл с ПК")
    if not path:
        return
    name = os.path.basename(path)
    dst = vfs.join(cwd, name)
    try:
        shutil.copy2(path, vfs._resolve(dst))
        refresh()
        d = _get_desktop(root)
        if d:
            d.notifications.push("Файл импортирован", name)
    except Exception as e:
        QMessageBox.warning(root, "Ошибка импорта", str(e))