"""
MountOS — Python REPL.

Интерактивный интерпретатор Python:
  • Ввод кода с многострочной поддержкой
  • Вывод stdout/stderr
  • История команд (стрелка вверх)
  • Автодополнение по Tab
  • Постоянное пространство имён (переменные сохраняются)
  • Сниппеты — быстрые вставки
  • Сохранение кода в VFS
  • Подсветка синтаксиса
"""

import sys
import io
import os
import traceback
import time
from contextlib import redirect_stdout, redirect_stderr

from PySide6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QLabel,
                                QPushButton, QTextEdit, QLineEdit,
                                QListWidget, QListWidgetItem, QScrollArea,
                                QFrame, QMessageBox, QInputDialog, QSplitter,
                                QSizePolicy, QComboBox, QCheckBox)
from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtGui import (QFont, QIcon, QColor, QTextCharFormat,
                            QSyntaxHighlighter, QTextCursor)

from ui.icons import get_icon
from ui.settings_state import state

APP_NAME = "Python REPL"
APP_ICON = "terminal"
APP_VERSION = "1.0"
APP_AUTHOR = "MountOS"


HISTORY_PATH = "/Documents/repl_history.json"
SCRIPTS_DIR = "/Documents/REPL_scripts"


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
#  Подсветка синтаксиса
# ============================================================

class PythonHighlighter(QSyntaxHighlighter):
    def __init__(self, document):
        super().__init__(document)
        import re
        self.rules = []

        # Ключевые слова
        kw_fmt = QTextCharFormat()
        kw_fmt.setForeground(QColor("#6EC6FF"))
        kw_fmt.setFontWeight(QFont.Bold)
        keywords = [
            "and", "as", "assert", "async", "await", "break", "class",
            "continue", "def", "del", "elif", "else", "except", "finally",
            "for", "from", "global", "if", "import", "in", "is", "lambda",
            "nonlocal", "not", "or", "pass", "raise", "return", "try",
            "while", "with", "yield", "True", "False", "None",
            "self", "cls",
        ]
        for kw in keywords:
            self.rules.append((re.compile(r"\b" + kw + r"\b"), kw_fmt))

        # Числа
        num_fmt = QTextCharFormat()
        num_fmt.setForeground(QColor("#FFB86C"))
        self.rules.append((re.compile(r"\b[0-9]+\.?[0-9]*\b"), num_fmt))

        # Строки
        str_fmt = QTextCharFormat()
        str_fmt.setForeground(QColor("#6EE7B7"))
        self.rules.append((re.compile(r"'[^']*'"), str_fmt))
        self.rules.append((re.compile(r'"[^"]*"'), str_fmt))

        # Комментарии
        com_fmt = QTextCharFormat()
        com_fmt.setForeground(QColor("#8B95A5"))
        com_fmt.setFontItalic(True)
        self.rules.append((re.compile(r"#[^\n]*"), com_fmt))

        # Встроенные
        builtin_fmt = QTextCharFormat()
        builtin_fmt.setForeground(QColor("#FF6B8A"))
        builtins = [
            "print", "len", "range", "str", "int", "float", "list", "dict",
            "set", "tuple", "open", "type", "isinstance", "hasattr",
            "getattr", "setattr", "super", "input", "enumerate", "zip",
            "map", "filter", "sum", "min", "max", "abs", "round",
        ]
        for b in builtins:
            self.rules.append((re.compile(r"\b" + b + r"\b"), builtin_fmt))

    def highlightBlock(self, text):
        for pattern, fmt in self.rules:
            for m in pattern.finditer(text):
                self.setFormat(m.start(), m.end() - m.start(), fmt)


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

    # Пространство имён
    namespace = {
        "__name__": "__repl__",
        "__doc__": None,
    }

    st = {
        "history": [],       # команды для стрелок
        "history_idx": -1,
        "multiline": "",     # для многострочных блоков
        "waiting_more": False,
    }

    # ============================================================
    #  Левая панель — история + скрипты
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

    title = QLabel("🐍  Python REPL")
    title.setStyleSheet("color: white; font-size: 16px; font-weight: 600; padding: 2px;")
    sl.addWidget(title)

    info = QLabel(f"Python {sys.version.split()[0]}")
    info.setStyleSheet("""
        color: rgba(255,255,255,0.55);
        font-size: 11px;
        padding: 4px 8px;
        background: rgba(0,0,0,0.20);
        border-radius: 8px;
    """)
    sl.addWidget(info)

    # Кнопки
    clear_ns_btn = QPushButton("🧹  Очистить переменные")
    clear_ns_btn.setCursor(Qt.PointingHandCursor)
    clear_ns_btn.setFixedHeight(34)
    clear_ns_btn.setStyleSheet("""
        QPushButton {
            background: rgba(255,107,138,0.15);
            color: #FFA0B4;
            border: 1px solid rgba(255,107,138,0.45);
            border-radius: 8px;
            font-size: 11px;
        }
        QPushButton:hover { background: rgba(255,107,138,0.35); color: white; }
    """)
    sl.addWidget(clear_ns_btn)

    save_script_btn = QPushButton("💾  Сохранить скрипт")
    save_script_btn.setCursor(Qt.PointingHandCursor)
    save_script_btn.setFixedHeight(34)
    save_script_btn.setStyleSheet("""
        QPushButton {
            background: rgba(110,231,183,0.18);
            color: white;
            border: 1px solid rgba(110,231,183,0.50);
            border-radius: 8px;
            font-size: 11px;
        }
        QPushButton:hover { background: rgba(110,231,183,0.38); }
    """)
    sl.addWidget(save_script_btn)

    # Переменные
    vars_lbl = QLabel("ПЕРЕМЕННЫЕ")
    vars_lbl.setStyleSheet("""
        color: rgba(255,255,255,0.45);
        font-size: 10px;
        font-weight: 700;
        letter-spacing: 1.5px;
        padding-top: 8px;
    """)
    sl.addWidget(vars_lbl)

    vars_list = QListWidget()
    vars_list.setStyleSheet("""
        QListWidget {
            background: rgba(0,0,0,0.20);
            color: white;
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 10px;
            padding: 4px;
            font-size: 11px;
            font-family: Consolas, monospace;
            outline: none;
        }
        QListWidget::item { padding: 5px 8px; border-radius: 4px; }
        QListWidget::item:hover { background: rgba(255,255,255,0.08); }
    """)
    sl.addWidget(vars_list, 1)

    # Сниппеты
    snippets_lbl = QLabel("СНИППЕТЫ")
    snippets_lbl.setStyleSheet(vars_lbl.styleSheet())
    sl.addWidget(snippets_lbl)

    snippets = [
        ("Hello World",       'print("Hello, World!")'),
        ("Цикл for",          'for i in range(10):\n    print(i)'),
        ("Функция",           'def foo(x):\n    return x * 2\n\nprint(foo(21))'),
        ("Класс",             'class Foo:\n    def __init__(self, name):\n        self.name = name\n    def greet(self):\n        return f"Привет, {self.name}"\n\nf = Foo("Мир")\nprint(f.greet())'),
        ("Список (list comp)",'squares = [x**2 for x in range(10)]\nprint(squares)'),
        ("Словарь",           'd = {"a": 1, "b": 2}\nfor k, v in d.items():\n    print(k, v)'),
        ("Try/except",        'try:\n    x = 1 / 0\nexcept ZeroDivisionError as e:\n    print(f"Ошибка: {e}")'),
        ("Файл (VFS)",        '# Работа с VFS MountOS\nimport mountos\nmountos.fs.write("/Documents/test.txt", "Hello")\nprint(mountos.fs.read("/Documents/test.txt"))'),
    ]

    snippets_list = QListWidget()
    snippets_list.setStyleSheet(vars_list.styleSheet())
    snippets_list.setFixedHeight(160)
    for name, code in snippets:
        item = QListWidgetItem(f"⚡ {name}")
        item.setData(Qt.UserRole, code)
        snippets_list.addItem(item)
    sl.addWidget(snippets_list)

    h.addWidget(side)

    # ============================================================
    #  Центр — REPL
    # ============================================================
    center = QWidget()
    cl = QVBoxLayout(center)
    cl.setContentsMargins(0, 0, 0, 0)
    cl.setSpacing(0)

    # Заголовок
    topbar = QWidget()
    topbar.setFixedHeight(52)
    topbar.setStyleSheet("""
        background: rgba(255,255,255,0.04);
        border-bottom: 1px solid rgba(255,255,255,0.08);
    """)
    tbl = QHBoxLayout(topbar)
    tbl.setContentsMargins(16, 8, 16, 8)

    topbar_title = QLabel("Интерактивная консоль")
    topbar_title.setStyleSheet("""
        color: white;
        font-size: 14px;
        font-weight: 600;
    """)
    tbl.addWidget(topbar_title)
    tbl.addStretch(1)

    clear_btn = QPushButton("🗑  Очистить вывод")
    clear_btn.setFixedHeight(30)
    clear_btn.setCursor(Qt.PointingHandCursor)
    clear_btn.setStyleSheet("""
        QPushButton {
            background: rgba(255,255,255,0.06);
            color: white;
            border: 1px solid rgba(255,255,255,0.12);
            border-radius: 8px;
            padding: 4px 12px;
            font-size: 11px;
        }
        QPushButton:hover { background: rgba(255,255,255,0.18); }
    """)
    tbl.addWidget(clear_btn)

    cl.addWidget(topbar)

    # Output
    output = QTextEdit()
    output.setReadOnly(True)
    output.setStyleSheet("""
        QTextEdit {
            background: rgba(0,0,0,0.35);
            color: #E0E6F0;
            border: none;
            padding: 16px;
            font-family: 'Consolas', 'Courier New', monospace;
            font-size: 13px;
            line-height: 1.5;
        }
    """)
    cl.addWidget(output, 1)

    # Ввод
    input_wrap = QWidget()
    input_wrap.setFixedHeight(50)
    input_wrap.setStyleSheet("""
        background: rgba(255,255,255,0.04);
        border-top: 1px solid rgba(255,255,255,0.08);
    """)
    iw = QHBoxLayout(input_wrap)
    iw.setContentsMargins(16, 8, 16, 8)
    iw.setSpacing(8)

    prompt_lbl = QLabel(">>>")
    prompt_lbl.setFixedWidth(30)
    prompt_lbl.setStyleSheet("""
        color: #6EE7B7;
        font-family: Consolas, monospace;
        font-size: 15px;
        font-weight: 600;
    """)
    iw.addWidget(prompt_lbl)

    input_edit = QLineEdit()
    input_edit.setPlaceholderText("Введи код на Python и нажми Enter")
    input_edit.setStyleSheet("""
        QLineEdit {
            background: transparent;
            color: white;
            border: none;
            padding: 4px;
            font-family: Consolas, monospace;
            font-size: 14px;
        }
    """)
    iw.addWidget(input_edit, 1)

    run_btn = QPushButton("▶  Run")
    run_btn.setFixedSize(90, 34)
    run_btn.setCursor(Qt.PointingHandCursor)
    run_btn.setStyleSheet("""
        QPushButton {
            background: rgba(110,198,255,0.22);
            color: white;
            border: 1px solid rgba(110,198,255,0.55);
            border-radius: 8px;
            font-size: 12px;
            font-weight: 600;
        }
        QPushButton:hover { background: rgba(110,198,255,0.42); }
    """)
    iw.addWidget(run_btn)

    cl.addWidget(input_wrap)

    h.addWidget(center, 1)

    # ============================================================
    #  Логика
    # ============================================================

    def append_output(text: str, color: str = "#E0E6F0"):
        """Добавляет текст с цветом."""
        cursor = output.textCursor()
        cursor.movePosition(QTextCursor.End)

        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))
        cursor.insertText(text, fmt)
        cursor.insertText("\n")
        output.setTextCursor(cursor)
        output.ensureCursorVisible()

    def refresh_vars():
        vars_list.clear()
        for k in sorted(namespace.keys()):
            if k.startswith("__") and k.endswith("__"):
                continue
            v = namespace[k]
            try:
                type_name = type(v).__name__
                if isinstance(v, (list, tuple, dict, set, str)):
                    preview = str(v)[:30]
                    text = f"{k}: {type_name} = {preview}"
                elif callable(v):
                    text = f"{k}: {type_name} {getattr(v, '__name__', '')}"
                else:
                    text = f"{k}: {type_name} = {v}"
            except Exception:
                text = f"{k} = <?>"
            item = QListWidgetItem(text)
            vars_list.addItem(item)

    def run_code(code: str):
        """Выполняет код и печатает результат."""
        if not code.strip():
            return

        # История
        st["history"].append(code)
        st["history_idx"] = len(st["history"])

        # Эхо
        append_output(f">>> {code}", "#6EE7B7")

        # Перехват stdout/stderr
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        captured = io.StringIO()
        captured_err = io.StringIO()

        try:
            sys.stdout = captured
            sys.stderr = captured_err

            # Пытаемся как выражение
            try:
                result = eval(code, namespace)
                if result is not None:
                    print(repr(result))
            except SyntaxError:
                # Многострочный код или statement
                exec(code, namespace)

        except Exception:
            tb = traceback.format_exc()
            captured_err.write(tb)
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr

        # Вывод
        out = captured.getvalue()
        err = captured_err.getvalue()

        if out:
            for line in out.rstrip().split("\n"):
                append_output(line, "#E0E6F0")
        if err:
            for line in err.rstrip().split("\n"):
                append_output(line, "#FFA0B4")

        if not out and not err:
            append_output("(без вывода)", "#8B95A5")

        refresh_vars()

    def on_run():
        code = input_edit.text()
        input_edit.clear()

        # Многострочный режим
        if st["waiting_more"]:
            st["multiline"] += "\n" + code
            if code.strip() == "":
                # Пустая строка — конец блока
                full = st["multiline"]
                st["multiline"] = ""
                st["waiting_more"] = False
                prompt_lbl.setText(">>>")
                run_code(full)
            else:
                append_output(f"... {code}", "#8B95A5")
            return

        # Проверяем, нужно ли продолжение
        if code.rstrip().endswith(":") or (code.strip().startswith(("def ", "class ", "if ", "for ", "while ", "try:", "with ", "except")) and code.strip().endswith(":")):
            st["multiline"] = code
            st["waiting_more"] = True
            prompt_lbl.setText("...")
            append_output(f">>> {code}", "#6EE7B7")
            return

        # Обычное выполнение
        run_code(code)

    def on_key_press(event):
        """Обработка стрелок вверх/вниз для истории."""
        if event.key() == Qt.Key_Up:
            if st["history"] and st["history_idx"] > 0:
                st["history_idx"] -= 1
                input_edit.setText(st["history"][st["history_idx"]])
            return
        if event.key() == Qt.Key_Down:
            if st["history"]:
                if st["history_idx"] < len(st["history"]) - 1:
                    st["history_idx"] += 1
                    input_edit.setText(st["history"][st["history_idx"]])
                else:
                    st["history_idx"] = len(st["history"])
                    input_edit.clear()
            return
        if event.key() == Qt.Key_L and event.modifiers() & Qt.ControlModifier:
            output.clear()
            return

        # Стандартная обработка
        QLineEdit.keyPressEvent(input_edit, event)

    input_edit.keyPressEvent = on_key_press

    input_edit.returnPressed.connect(on_run)
    run_btn.clicked.connect(on_run)

    def clear_output():
        output.clear()
        append_output(f"Python {sys.version.split()[0]} on {sys.platform}",
                       "#6EC6FF")
        append_output('Введи код и нажми Enter. Ctrl+L — очистить.',
                       "#8B95A5")
        append_output("", "#E0E6F0")

    def clear_namespace():
        ans = QMessageBox.question(root, "Очистить переменные",
            "Удалить все переменные из памяти?",
            QMessageBox.Yes | QMessageBox.No)
        if ans == QMessageBox.Yes:
            namespace.clear()
            namespace["__name__"] = "__repl__"
            namespace["__doc__"] = None
            refresh_vars()
            append_output("Пространство имён очищено", "#6EC6FF")

    def save_script():
        code, ok = QInputDialog.getMultiLineText(
            root, "Сохранить скрипт",
            "Введи код для сохранения:")
        if not ok or not code.strip():
            return
        name, ok = QInputDialog.getText(
            root, "Имя файла", "Имя (без .py):", text="script")
        if not ok or not name.strip():
            return

        if vfs is None:
            return
        try:
            vfs.mkdir(SCRIPTS_DIR)
            path = f"{SCRIPTS_DIR}/{name.strip()}.py"
            vfs.write_text(path, code)
            append_output(f"✓ Скрипт сохранён: {path}", "#6EE7B7")
            if desktop and hasattr(desktop, "notifications"):
                desktop.notifications.push("REPL", f"Скрипт: {name}")
        except Exception as e:
            QMessageBox.warning(root, "Ошибка", str(e))

    def on_snippet_click(item):
        code = item.data(Qt.UserRole)
        if code:
            input_edit.setText(code.split("\n")[0])
            if "\n" in code:
                # Многострочный — сразу выполнить
                input_edit.clear()
                run_code(code)

    clear_btn.clicked.connect(clear_output)
    clear_ns_btn.clicked.connect(clear_namespace)
    save_script_btn.clicked.connect(save_script)
    snippets_list.itemClicked.connect(on_snippet_click)

    # Приветствие
    clear_output()
    refresh_vars()

    QTimer.singleShot(200, input_edit.setFocus)

    return root