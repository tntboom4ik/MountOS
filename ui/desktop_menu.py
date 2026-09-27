from PySide6.QtWidgets import QMenu, QInputDialog
from PySide6.QtGui import QAction

from ui.context_menu import make_menu
from ui.widgets import WIDGET_FACTORY, WIDGET_NAMES


def show_desktop_menu(desktop, global_pos):
    m = make_menu(desktop)

    sub_w = m.addMenu("➕ Добавить виджет")
    sub_w.setStyleSheet(m.styleSheet())
    for wid, name in WIDGET_NAMES.items():
        a = QAction(name, sub_w)
        a.triggered.connect(lambda _, w=wid: desktop.add_widget(w))
        sub_w.addAction(a)

    sub_s = m.addMenu("🔗 Создать ярлык приложения")
    sub_s.setStyleSheet(m.styleSheet())
    for app_id, info in desktop.registry.apps.items():
        a = QAction(f"  {info.name}", sub_s)
        a.triggered.connect(lambda _, i=app_id: desktop.add_app_shortcut(i))
        sub_s.addAction(a)

    m.addSeparator()

    a_file = m.addAction("📄 Создать текстовый файл")
    a_file.triggered.connect(lambda: _create_text_file(desktop))

    a_folder = m.addAction("📁 Создать папку")
    a_folder.triggered.connect(lambda: _create_folder(desktop))

    m.addSeparator()

    a_clean = m.addAction("🧹 Скрыть все окна")
    a_clean.triggered.connect(lambda: [w.hide() for w in desktop.windows])

    m.addSeparator()

    a_install = m.addAction("📦 Установить приложение (.py)")
    a_install.triggered.connect(desktop.install_app)

    m.exec(global_pos)


def _create_text_file(desktop):
    name, ok = QInputDialog.getText(desktop, "Новый файл", "Имя:", text="новый.txt")
    if not ok or not name.strip():
        return
    path = "/Documents/" + name.strip()
    if not desktop.vfs.exists(path):
        desktop.vfs.write_text(path, "")
        desktop.add_file_shortcut(path, name.strip())
        desktop.notifications.push("Создан файл", path)


def _create_folder(desktop):
    name, ok = QInputDialog.getText(desktop, "Новая папка", "Имя:", text="Папка")
    if not ok or not name.strip():
        return
    path = "/" + name.strip()
    desktop.vfs.mkdir(path)
    desktop.notifications.push("Создана папка", path)