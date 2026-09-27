"""
MountOS — Текстовый редактор.
Открытие/сохранение в VFS, поиск/замена, шрифты, перенос строк.
"""
import os
import re
from PySide6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QLabel,
                                QPushButton, QTextEdit, QLineEdit,
                                QSpinBox, QMessageBox, QCheckBox,
                                QFontComboBox, QDialog, QFormLayout,
                                QSizePolicy, QApplication, QInputDialog)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QTextCursor, QTextDocument

from ui.icons import get_icon
from ui.settings_state import state

APP_NAME = "Текстовый редактор"
APP_ICON = "editor"
APP_VERSION = "1.0"
APP_AUTHOR = "MountOS"


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

    for top in QApplication.topLevelWidgets():
        if hasattr(top, "notifications") and hasattr(top, "open_app"):
            return top
        ref = getattr(top, "desktop_ref", None)
        if ref is not None:
            return ref
    return None


# ============================================================
#  Редактор с горячими клавишами
# ============================================================

class MountTextEdit(QTextEdit):
    """QTextEdit с кастомными Ctrl-хоткеями. Наследование — правильный способ."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._on_save = None
        self._on_save_as = None
        self._on_open = None
        self._on_new = None
        self._on_find = None

    def set_callbacks(self, on_save=None, on_save_as=None,
                      on_open=None, on_new=None, on_find=None):
        self._on_save = on_save
        self._on_save_as = on_save_as
        self._on_open = on_open
        self._on_new = on_new
        self._on_find = on_find

    def keyPressEvent(self, e):
        ctrl = bool(e.modifiers() & Qt.ControlModifier)
        shift = bool(e.modifiers() & Qt.ShiftModifier)

        if ctrl and e.key() == Qt.Key_S:
            if shift:
                if self._on_save_as:
                    self._on_save_as()
            else:
                if self._on_save:
                    self._on_save()
            e.accept()
            return

        if ctrl and e.key() == Qt.Key_O:
            if self._on_open:
                self._on_open()
            e.accept()
            return

        if ctrl and e.key() == Qt.Key_N:
            if self._on_new:
                self._on_new()
            e.accept()
            return

        if ctrl and e.key() in (Qt.Key_F, Qt.Key_H):
            if self._on_find:
                self._on_find()
            e.accept()
            return

        super().keyPressEvent(e)


# ============================================================
#  Диалог поиска и замены
# ============================================================

class FindReplaceDialog(QDialog):
    def __init__(self, editor, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Найти и заменить")
        self.setModal(False)
        self.resize(440, 210)
        self.editor = editor

        self.setStyleSheet("""
            QDialog { background: #1A1F35; color: white; }
            QLabel { color: rgba(255,255,255,0.85); font-size: 12px; }
            QLineEdit {
                background: rgba(255,255,255,0.08);
                color: white;
                border: 1px solid rgba(255,255,255,0.15);
                border-radius: 8px;
                padding: 6px 10px;
                font-size: 12px;
            }
            QLineEdit:focus { border: 1px solid rgba(110,198,255,0.6); }
            QCheckBox { color: rgba(255,255,255,0.85); font-size: 11px; }
        """)

        form = QFormLayout(self)
        form.setContentsMargins(16, 16, 16, 16)
        form.setSpacing(10)

        self.find_edit = QLineEdit()
        form.addRow("Найти:", self.find_edit)

        self.replace_edit = QLineEdit()
        form.addRow("Заменить:", self.replace_edit)

        self.case_cb = QCheckBox("Учитывать регистр")
        form.addRow("", self.case_cb)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        prev_btn = QPushButton("◀ Ранее")
        prev_btn.setCursor(Qt.PointingHandCursor)
        prev_btn.setStyleSheet(_dlg_btn_style())
        prev_btn.clicked.connect(self.find_prev)
        btn_row.addWidget(prev_btn)

        next_btn = QPushButton("Позже ▶")
        next_btn.setCursor(Qt.PointingHandCursor)
        next_btn.setStyleSheet(_dlg_btn_style())
        next_btn.clicked.connect(self.find_next)
        btn_row.addWidget(next_btn)

        repl_btn = QPushButton("Заменить")
        repl_btn.setCursor(Qt.PointingHandCursor)
        repl_btn.setStyleSheet(_dlg_btn_style(accent=True))
        repl_btn.clicked.connect(self.replace_one)
        btn_row.addWidget(repl_btn)

        repl_all_btn = QPushButton("Заменить всё")
        repl_all_btn.setCursor(Qt.PointingHandCursor)
        repl_all_btn.setStyleSheet(_dlg_btn_style(accent=True))
        repl_all_btn.clicked.connect(self.replace_all)
        btn_row.addWidget(repl_all_btn)

        form.addRow("", btn_row)

        self.status = QLabel("")
        self.status.setStyleSheet("color: rgba(255,255,255,0.55); font-size: 11px;")
        form.addRow("", self.status)

    def _flags(self):
        flags = QTextDocument.FindFlags()
        if self.case_cb.isChecked():
            flags |= QTextDocument.FindCaseSensitively
        return flags

    def _search_text(self):
        text = self.find_edit.text()
        if not text:
            self.status.setText("Введи что искать")
            return None
        return text

    def find_next(self):
        text = self._search_text()
        if text is None:
            return
        found = self.editor.find(text, self._flags())
        if not found:
            cursor = self.editor.textCursor()
            cursor.movePosition(QTextCursor.Start)
            self.editor.setTextCursor(cursor)
            found = self.editor.find(text, self._flags())
        self.status.setText("" if found else "Не найдено")

    def find_prev(self):
        text = self._search_text()
        if text is None:
            return
        flags = self._flags() | QTextDocument.FindBackward
        found = self.editor.find(text, flags)
        if not found:
            cursor = self.editor.textCursor()
            cursor.movePosition(QTextCursor.End)
            self.editor.setTextCursor(cursor)
            found = self.editor.find(text, flags)
        self.status.setText("" if found else "Не найдено")

    def replace_one(self):
        text = self._search_text()
        if text is None:
            return
        if self.editor.textCursor().hasSelection():
            sel = self.editor.textCursor().selectedText()
            if self.case_cb.isChecked():
                match = (sel == text)
            else:
                match = (sel.lower() == text.lower())
            if match:
                self.editor.insertPlainText(self.replace_edit.text())
        self.find_next()

    def replace_all(self):
        text = self._search_text()
        if text is None:
            return
        content = self.editor.toPlainText()
        replacement = self.replace_edit.text()

        if self.case_cb.isChecked():
            count = content.count(text)
            new_content = content.replace(text, replacement)
        else:
            pattern = re.compile(re.escape(text), re.IGNORECASE)
            count = len(pattern.findall(content))
            new_content = pattern.sub(replacement, content)

        if count == 0:
            self.status.setText("Не найдено")
            return

        self.editor.setPlainText(new_content)
        self.status.setText(f"Заменено вхождений: {count}")


def _dlg_btn_style(accent=False):
    if accent:
        return """
            QPushButton {
                background: rgba(110,198,255,0.22);
                color: white;
                border: 1px solid rgba(110,198,255,0.55);
                border-radius: 8px;
                padding: 6px 12px;
                font-size: 11px;
            }
            QPushButton:hover { background: rgba(110,198,255,0.42); }
        """
    return """
        QPushButton {
            background: rgba(255,255,255,0.08);
            color: white;
            border: 1px solid rgba(255,255,255,0.14);
            border-radius: 8px;
            padding: 6px 12px;
            font-size: 11px;
        }
        QPushButton:hover { background: rgba(255,255,255,0.20); }
    """


# ============================================================
#  Основное приложение
# ============================================================

def build():
    root = QWidget()
    h = QHBoxLayout(root)
    h.setContentsMargins(0, 0, 0, 0)
    h.setSpacing(0)

    main = QWidget()
    ml = QVBoxLayout(main)
    ml.setContentsMargins(16, 12, 16, 14)
    ml.setSpacing(10)

    # ---------------- Верхняя панель ----------------
    top = QHBoxLayout()
    top.setSpacing(6)

    open_btn = QPushButton("Открыть")
    open_btn.setCursor(Qt.PointingHandCursor)
    open_btn.setFixedHeight(32)
    open_btn.setStyleSheet(_btn_style())
    top.addWidget(open_btn)

    save_btn = QPushButton("Сохранить")
    save_btn.setCursor(Qt.PointingHandCursor)
    save_btn.setFixedHeight(32)
    save_btn.setStyleSheet(_btn_style(accent=True))
    top.addWidget(save_btn)

    save_as_btn = QPushButton("Сохранить как…")
    save_as_btn.setCursor(Qt.PointingHandCursor)
    save_as_btn.setFixedHeight(32)
    save_as_btn.setStyleSheet(_btn_style())
    top.addWidget(save_as_btn)

    top.addSpacing(12)

    new_btn = QPushButton("＋ Новый")
    new_btn.setCursor(Qt.PointingHandCursor)
    new_btn.setFixedHeight(32)
    new_btn.setStyleSheet(_btn_style())
    top.addWidget(new_btn)

    top.addSpacing(12)

    find_btn = QPushButton("Найти / Заменить")
    find_btn.setCursor(Qt.PointingHandCursor)
    find_btn.setFixedHeight(32)
    find_btn.setStyleSheet(_btn_style())
    top.addWidget(find_btn)

    top.addStretch(1)

    path_lbl = QLabel("Новый файл")
    path_lbl.setStyleSheet("""
        color: rgba(255,255,255,0.55);
        font-size: 12px;
        font-family: Consolas, monospace;
    """)
    path_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
    path_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
    top.addWidget(path_lbl)

    ml.addLayout(top)

    # ---------------- Панель форматирования ----------------
    fmt = QHBoxLayout()
    fmt.setSpacing(6)

    font_combo = QFontComboBox()
    font_combo.setCurrentFont(QFont("Consolas"))
    font_combo.setFixedWidth(180)
    font_combo.setStyleSheet(_combo_style())
    fmt.addWidget(font_combo)

    size_spin = QSpinBox()
    size_spin.setRange(8, 72)
    size_spin.setValue(13)
    size_spin.setFixedWidth(64)
    size_spin.setStyleSheet(_combo_style())
    fmt.addWidget(size_spin)

    fmt.addSpacing(8)

    bold_btn = QPushButton("B")
    bold_btn.setFixedSize(32, 32)
    bold_btn.setCheckable(True)
    bold_btn.setCursor(Qt.PointingHandCursor)
    bold_btn.setStyleSheet(_fmt_btn_style(bold=True))
    fmt.addWidget(bold_btn)

    italic_btn = QPushButton("I")
    italic_btn.setFixedSize(32, 32)
    italic_btn.setCheckable(True)
    italic_btn.setCursor(Qt.PointingHandCursor)
    italic_btn.setStyleSheet(_fmt_btn_style(italic=True))
    fmt.addWidget(italic_btn)

    fmt.addSpacing(12)

    wrap_cb = QCheckBox("Перенос строк")
    wrap_cb.setChecked(True)
    wrap_cb.setStyleSheet("""
        QCheckBox { color: rgba(255,255,255,0.75); font-size: 11px; }
        QCheckBox::indicator { width: 16px; height: 16px; }
    """)
    fmt.addWidget(wrap_cb)

    fmt.addStretch(1)

    counter = QLabel("Строк: 1    Символов: 0")
    counter.setStyleSheet("color: rgba(255,255,255,0.45); font-size: 11px;")
    fmt.addWidget(counter)

    ml.addLayout(fmt)

    # ---------------- Редактор ----------------
    editor = MountTextEdit()
    editor.setStyleSheet("""
        QTextEdit {
            background: rgba(0,0,0,0.28);
            color: white;
            border: 1px solid rgba(255,255,255,0.10);
            border-radius: 12px;
            padding: 14px;
            font-family: Consolas, monospace;
            font-size: 13px;
            selection-background-color: rgba(110,198,255,0.45);
        }
    """)
    ml.addWidget(editor, 1)

    h.addWidget(main, 1)

    # ============================================================
    #  Логика
    # ============================================================

    state_obj = {
        "path": None,
        "modified": False,
        "find_dlg": None,
    }

    # ---------------- Счётчик ----------------
    def update_counter():
        text = editor.toPlainText()
        lines = text.count("\n") + 1
        counter.setText(f"Строк: {lines}    Символов: {len(text)}")

    editor.textChanged.connect(update_counter)
    update_counter()

    # ---------------- Заголовок ----------------
    def update_title():
        mark = " ●" if state_obj["modified"] else ""
        if state_obj["path"]:
            path_lbl.setText(f"{state_obj['path']}{mark}")
        else:
            path_lbl.setText(f"Новый файл{mark}")

    def mark_modified():
        if not state_obj["modified"]:
            state_obj["modified"] = True
            update_title()

    editor.textChanged.connect(mark_modified)

    # ---------------- Открытие ----------------
    def open_file():
        vfs = _get_vfs(root)
        if vfs is None:
            QMessageBox.warning(root, "Ошибка", "VFS недоступна")
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
                    if name_low.endswith((
                            ".txt", ".md", ".log", ".json", ".py", ".html",
                            ".css", ".js", ".csv", ".ini", ".cfg", ".xml",
                            ".yml", ".yaml")):
                        files.append(it["path"])

        walk("/")

        if not files:
            QMessageBox.information(root, "Редактор",
                                    "В VFS нет текстовых файлов.")
            return

        choice, ok = QInputDialog.getItem(
            root, "Открыть файл", "Выбери файл из VFS:", files, 0, False)
        if not ok:
            return

        try:
            content = vfs.read_text(choice, "")
        except Exception as e:
            QMessageBox.warning(root, "Ошибка", f"Не удалось открыть:\n{e}")
            return

        editor.blockSignals(True)
        editor.setPlainText(content)
        editor.blockSignals(False)
        state_obj["path"] = choice
        state_obj["modified"] = False
        update_title()
        update_counter()

        d = _get_desktop(root)
        if d:
            d.notifications.push("Открыт файл", choice)

    # ---------------- Сохранение ----------------
    def save_file():
        vfs = _get_vfs(root)
        if vfs is None:
            return
        path = state_obj["path"]
        if not path:
            return save_as()
        try:
            vfs.write_text(path, editor.toPlainText())
            state_obj["modified"] = False
            update_title()
            d = _get_desktop(root)
            if d:
                d.notifications.push("Файл сохранён", path)
        except Exception as e:
            QMessageBox.warning(root, "Ошибка", f"Не удалось сохранить:\n{e}")

    def save_as():
        vfs = _get_vfs(root)
        if vfs is None:
            return
        name, ok = QInputDialog.getText(
            root, "Сохранить как",
            "Путь в VFS (например, /Documents/мой.txt):",
            text="/Documents/новый.txt")
        if not ok or not name.strip():
            return
        path = name.strip()
        try:
            vfs.write_text(path, editor.toPlainText())
        except Exception as e:
            QMessageBox.warning(root, "Ошибка", f"Не удалось сохранить:\n{e}")
            return
        state_obj["path"] = path
        state_obj["modified"] = False
        update_title()
        d = _get_desktop(root)
        if d:
            d.notifications.push("Файл сохранён", path)

    # ---------------- Новый ----------------
    def new_file():
        if state_obj["modified"]:
            ans = QMessageBox.question(root, "Новый файл",
                "Текущий файл не сохранён. Продолжить?",
                QMessageBox.Yes | QMessageBox.No)
            if ans != QMessageBox.Yes:
                return
        editor.clear()
        state_obj["path"] = None
        state_obj["modified"] = False
        update_title()

    # ---------------- Поиск ----------------
    def open_find():
        if state_obj["find_dlg"] is None or not state_obj["find_dlg"].isVisible():
            dlg = FindReplaceDialog(editor, root)
            state_obj["find_dlg"] = dlg
            dlg.show()
            dlg.raise_()
            dlg.activateWindow()
        else:
            state_obj["find_dlg"].raise_()
            state_obj["find_dlg"].activateWindow()

    # ---------------- Формат ----------------
    def apply_format():
        cursor = editor.textCursor()
        fmt_obj = cursor.charFormat()
        fmt_obj.setFontFamily(font_combo.currentFont().family())
        fmt_obj.setFontPointSize(size_spin.value())
        fmt_obj.setFontWeight(QFont.Bold if bold_btn.isChecked() else QFont.Normal)
        fmt_obj.setFontItalic(italic_btn.isChecked())

        if not cursor.hasSelection():
            editor.setCurrentCharFormat(fmt_obj)
        else:
            cursor.mergeCharFormat(fmt_obj)
            editor.mergeCurrentCharFormat(fmt_obj)

    font_combo.currentFontChanged.connect(lambda _: apply_format())
    size_spin.valueChanged.connect(lambda _: apply_format())
    bold_btn.toggled.connect(lambda _: apply_format())
    italic_btn.toggled.connect(lambda _: apply_format())

    # ---------------- Перенос строк ----------------
    def set_wrap(state_val):
        if state_val:
            editor.setLineWrapMode(QTextEdit.WidgetWidth)
        else:
            editor.setLineWrapMode(QTextEdit.NoWrap)

    wrap_cb.stateChanged.connect(lambda v: set_wrap(bool(v)))
    set_wrap(True)

    # ---------------- Колбэки на редактор ----------------
    editor.set_callbacks(
        on_save=save_file,
        on_save_as=save_as,
        on_open=open_file,
        on_new=new_file,
        on_find=open_find,
    )

    # ---------------- Кнопки ----------------
    open_btn.clicked.connect(open_file)
    save_btn.clicked.connect(save_file)
    save_as_btn.clicked.connect(save_as)
    new_btn.clicked.connect(new_file)
    find_btn.clicked.connect(open_find)

    update_title()
    editor.setFocus()

    return root


# ============================================================
#  Стили
# ============================================================

def _btn_style(accent=False):
    if accent:
        return """
            QPushButton {
                background: rgba(110,198,255,0.22);
                color: white;
                border: 1px solid rgba(110,198,255,0.55);
                border-radius: 8px;
                padding: 4px 14px;
                font-size: 12px;
            }
            QPushButton:hover { background: rgba(110,198,255,0.42); }
        """
    return """
        QPushButton {
            background: rgba(255,255,255,0.08);
            color: white;
            border: 1px solid rgba(255,255,255,0.14);
            border-radius: 8px;
            padding: 4px 14px;
            font-size: 12px;
        }
        QPushButton:hover { background: rgba(255,255,255,0.20); }
        QPushButton:pressed { background: rgba(110,198,255,0.35); }
    """


def _combo_style():
    return """
        QComboBox, QFontComboBox, QSpinBox {
            background: rgba(255,255,255,0.08);
            color: white;
            border: 1px solid rgba(255,255,255,0.14);
            border-radius: 8px;
            padding: 5px 8px;
            font-size: 12px;
        }
        QComboBox:hover, QFontComboBox:hover, QSpinBox:hover {
            background: rgba(255,255,255,0.16);
        }
        QComboBox QAbstractItemView {
            background: rgba(28,34,54,0.98);
            color: white;
            selection-background-color: rgba(110,198,255,0.35);
            border: 1px solid rgba(255,255,255,0.15);
        }
    """


def _fmt_btn_style(bold=False, italic=False):
    weight = "700" if bold else "500"
    style = "italic" if italic else "normal"
    return f"""
        QPushButton {{
            background: rgba(255,255,255,0.06);
            color: white;
            border: 1px solid rgba(255,255,255,0.12);
            border-radius: 8px;
            font-size: 14px;
            font-weight: {weight};
            font-style: {style};
        }}
        QPushButton:hover {{
            background: rgba(255,255,255,0.18);
        }}
        QPushButton:checked {{
            background: rgba(110,198,255,0.32);
            border: 1px solid rgba(110,198,255,0.70);
        }}
    """