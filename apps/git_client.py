"""
MountOS — MountGit.

Git-клиент через subprocess:
  • Открытие локальных репозиториев
  • Просмотр статуса, истории коммитов
  • Ветки (переключение, создание, удаление)
  • Commit, Push, Pull
  • Diff изменений
  • Клонирование по URL
  • Красивый интерфейс

Требуется git в PATH (обычно уже установлен).
"""

import os
import subprocess
import sys
from datetime import datetime

from PySide6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QLabel,
                                QPushButton, QListWidget, QListWidgetItem,
                                QLineEdit, QTextEdit, QFileDialog, QMessageBox,
                                QTabWidget, QSplitter, QComboBox, QScrollArea,
                                QFrame, QSizePolicy, QDialog, QDialogButtonBox,
                                QFormLayout, QInputDialog)
from PySide6.QtCore import Qt, QTimer, QThread, Signal, QSize
from PySide6.QtGui import QFont, QIcon, QColor

from ui.icons import get_icon
from ui.settings_state import state

APP_NAME = "MountGit"
APP_ICON = "terminal"
APP_VERSION = "1.0"
APP_AUTHOR = "MountOS"


LAST_REPO_PATH = "/Documents/git_last_repo.txt"


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


def _flags():
    if sys.platform.startswith("win"):
        return subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
    return 0


def run_git(repo_path: str, *args, timeout=15) -> tuple:
    """Запускает git и возвращает (ok, stdout, stderr)."""
    try:
        result = subprocess.run(
            ["git", "-C", repo_path] + list(args),
            capture_output=True, text=True, timeout=timeout,
            creationflags=_flags(),
            encoding="utf-8", errors="replace")
        return (result.returncode == 0, result.stdout, result.stderr)
    except FileNotFoundError:
        return (False, "", "Git не найден в PATH. Установи git.")
    except subprocess.TimeoutExpired:
        return (False, "", "Превышено время выполнения git")
    except Exception as e:
        return (False, "", str(e))


def check_git_installed() -> tuple:
    """Проверяет, установлен ли git."""
    try:
        result = subprocess.run(
            ["git", "--version"],
            capture_output=True, text=True, timeout=5,
            creationflags=_flags())
        return (True, result.stdout.strip())
    except Exception:
        return (False, "")


# ============================================================
#  Воркер для асинхронного git
# ============================================================

class GitWorker(QThread):
    done = Signal(bool, str, str)   # ok, stdout, stderr

    def __init__(self, repo: str, *args, timeout=15):
        super().__init__()
        self.repo = repo
        self.args = args
        self.timeout = timeout

    def run(self):
        ok, out, err = run_git(self.repo, *self.args, timeout=self.timeout)
        self.done.emit(ok, out, err)


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

    st = {
        "repo_path": "",
        "worker": None,
    }

    # Проверяем git
    git_ok, git_version = check_git_installed()

    # Загружаем последний репозиторий
    if vfs:
        try:
            path = vfs.read_text(LAST_REPO_PATH, "").strip()
            if path and os.path.isdir(path):
                st["repo_path"] = path
        except Exception:
            pass

    # ============================================================
    #  Левая панель — управление репозиторием
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

    title = QLabel("🔗  MountGit")
    title.setStyleSheet("color: white; font-size: 16px; font-weight: 600; padding: 2px;")
    sl.addWidget(title)

    if not git_ok:
        warn = QLabel(
            "⚠ Git не найден в PATH\n\n"
            "Установи Git:\n"
            "https://git-scm.com/downloads\n\n"
            "После установки перезапусти MountOS."
        )
        warn.setStyleSheet("""
            background: rgba(255,107,138,0.15);
            color: #FFA0B4;
            border: 1px solid rgba(255,107,138,0.45);
            border-radius: 10px;
            padding: 12px;
            font-size: 12px;
        """)
        warn.setWordWrap(True)
        sl.addWidget(warn)

    git_lbl = QLabel(f"✓ {git_version}" if git_ok else "✗ git не найден")
    git_lbl.setStyleSheet(f"""
        color: {'#6EE7B7' if git_ok else '#FFA0B4'};
        font-size: 11px;
        padding: 4px;
        background: rgba(0,0,0,0.20);
        border-radius: 8px;
    """)
    sl.addWidget(git_lbl)

    # Кнопка открыть репозиторий
    open_btn = QPushButton("📂  Открыть репозиторий")
    open_btn.setCursor(Qt.PointingHandCursor)
    open_btn.setFixedHeight(38)
    open_btn.setStyleSheet("""
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
    sl.addWidget(open_btn)

    clone_btn = QPushButton("⬇  Клонировать с GitHub")
    clone_btn.setCursor(Qt.PointingHandCursor)
    clone_btn.setFixedHeight(38)
    clone_btn.setStyleSheet("""
        QPushButton {
            background: rgba(179,136,255,0.18);
            color: white;
            border: 1px solid rgba(179,136,255,0.50);
            border-radius: 10px;
            font-size: 12px;
        }
        QPushButton:hover { background: rgba(179,136,255,0.38); }
    """)
    sl.addWidget(clone_btn)

    # Путь
    path_lbl = QLabel("Репозиторий: не выбран")
    path_lbl.setStyleSheet("""
        color: rgba(255,255,255,0.55);
        font-size: 11px;
        font-family: Consolas, monospace;
        background: rgba(0,0,0,0.20);
        border-radius: 8px;
        padding: 8px;
    """)
    path_lbl.setWordWrap(True)
    sl.addWidget(path_lbl)

    # Ветки
    branch_lbl = QLabel("ВЕТКИ")
    branch_lbl.setStyleSheet("""
        color: rgba(255,255,255,0.45);
        font-size: 10px;
        font-weight: 700;
        letter-spacing: 1.5px;
        padding-top: 6px;
    """)
    sl.addWidget(branch_lbl)

    branches_list = QListWidget()
    branches_list.setStyleSheet("""
        QListWidget {
            background: rgba(0,0,0,0.20);
            color: white;
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 10px;
            padding: 4px;
            font-size: 12px;
            outline: none;
        }
        QListWidget::item { padding: 6px 10px; border-radius: 6px; }
        QListWidget::item:hover { background: rgba(255,255,255,0.08); }
        QListWidget::item:selected { background: rgba(110,198,255,0.30); }
    """)
    branches_list.setFixedHeight(140)
    sl.addWidget(branches_list)

    new_branch_btn = QPushButton("＋  Новая ветка")
    new_branch_btn.setCursor(Qt.PointingHandCursor)
    new_branch_btn.setFixedHeight(30)
    new_branch_btn.setStyleSheet("""
        QPushButton {
            background: rgba(255,255,255,0.06);
            color: white;
            border: 1px solid rgba(255,255,255,0.12);
            border-radius: 8px;
            font-size: 11px;
        }
        QPushButton:hover { background: rgba(255,255,255,0.18); }
    """)
    sl.addWidget(new_branch_btn)

    sl.addStretch(1)

    # Кнопки действий
    fetch_btn = QPushButton("🔄  Fetch")
    fetch_btn.setCursor(Qt.PointingHandCursor)
    fetch_btn.setFixedHeight(32)
    fetch_btn.setStyleSheet("""
        QPushButton {
            background: rgba(255,255,255,0.08);
            color: white;
            border: 1px solid rgba(255,255,255,0.12);
            border-radius: 8px;
            font-size: 11px;
        }
        QPushButton:hover { background: rgba(255,255,255,0.18); }
    """)
    sl.addWidget(fetch_btn)

    pull_btn = QPushButton("⬇  Pull")
    pull_btn.setCursor(Qt.PointingHandCursor)
    pull_btn.setFixedHeight(32)
    pull_btn.setStyleSheet(fetch_btn.styleSheet())
    sl.addWidget(pull_btn)

    push_btn = QPushButton("⬆  Push")
    push_btn.setCursor(Qt.PointingHandCursor)
    push_btn.setFixedHeight(32)
    push_btn.setStyleSheet("""
        QPushButton {
            background: rgba(110,231,183,0.18);
            color: white;
            border: 1px solid rgba(110,231,183,0.50);
            border-radius: 8px;
            font-size: 11px;
        }
        QPushButton:hover { background: rgba(110,231,183,0.38); }
    """)
    sl.addWidget(push_btn)

    h.addWidget(side)

    # ============================================================
    #  Центр — вкладки
    # ============================================================
    right = QWidget()
    rl = QVBoxLayout(right)
    rl.setContentsMargins(0, 0, 0, 0)
    rl.setSpacing(0)

    tabs = QTabWidget()
    tabs.setStyleSheet("""
        QTabWidget::pane { background: transparent; border: none; }
        QTabBar::tab {
            background: rgba(255,255,255,0.04);
            color: rgba(255,255,255,0.65);
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 8px;
            padding: 8px 16px;
            margin: 4px 2px;
            font-size: 12px;
        }
        QTabBar::tab:selected {
            background: rgba(110,198,255,0.22);
            color: white;
            border: 1px solid rgba(110,198,255,0.50);
        }
        QTabBar::tab:hover:!selected {
            background: rgba(255,255,255,0.10);
            color: white;
        }
    """)

    # ---- Вкладка: Status ----
    status_page = QWidget()
    spl = QVBoxLayout(status_page)
    spl.setContentsMargins(20, 20, 20, 20)
    spl.setSpacing(12)

    status_title = QLabel("Статус репозитория")
    status_title.setStyleSheet("color: white; font-size: 14px; font-weight: 600;")
    spl.addWidget(status_title)

    status_text = QTextEdit()
    status_text.setReadOnly(True)
    status_text.setStyleSheet("""
        QTextEdit {
            background: rgba(0,0,0,0.30);
            color: #E0E6F0;
            border: 1px solid rgba(255,255,255,0.10);
            border-radius: 12px;
            padding: 12px;
            font-family: Consolas, monospace;
            font-size: 12px;
        }
    """)
    spl.addWidget(status_text, 1)

    # Commit box
    commit_box = QWidget()
    commit_box.setStyleSheet("""
        QWidget {
            background: rgba(255,255,255,0.05);
            border: 1px solid rgba(255,255,255,0.10);
            border-radius: 12px;
        }
    """)
    cbl = QVBoxLayout(commit_box)
    cbl.setContentsMargins(14, 12, 14, 12)
    cbl.setSpacing(8)

    commit_lbl = QLabel("💾  Commit")
    commit_lbl.setStyleSheet("color: white; font-size: 13px; font-weight: 600; background: transparent; border: none;")
    cbl.addWidget(commit_lbl)

    commit_input = QLineEdit()
    commit_input.setPlaceholderText("Сообщение коммита…")
    commit_input.setStyleSheet("""
        QLineEdit {
            background: rgba(0,0,0,0.25);
            color: white;
            border: 1px solid rgba(255,255,255,0.12);
            border-radius: 8px;
            padding: 8px 12px;
            font-size: 13px;
        }
        QLineEdit:focus { border: 1px solid rgba(110,198,255,0.6); }
    """)
    cbl.addWidget(commit_input)

    commit_btn_row = QHBoxLayout()
    commit_btn_row.setSpacing(8)

    stage_all_btn = QPushButton("📦  git add .")
    stage_all_btn.setCursor(Qt.PointingHandCursor)
    stage_all_btn.setFixedHeight(34)
    stage_all_btn.setStyleSheet("""
        QPushButton {
            background: rgba(255,255,255,0.08);
            color: white;
            border: 1px solid rgba(255,255,255,0.12);
            border-radius: 8px;
            font-size: 11px;
            padding: 4px 14px;
        }
        QPushButton:hover { background: rgba(255,255,255,0.18); }
    """)
    commit_btn_row.addWidget(stage_all_btn)

    commit_go_btn = QPushButton("✓  Сделать commit")
    commit_go_btn.setCursor(Qt.PointingHandCursor)
    commit_go_btn.setFixedHeight(34)
    commit_go_btn.setStyleSheet("""
        QPushButton {
            background: rgba(110,198,255,0.22);
            color: white;
            border: 1px solid rgba(110,198,255,0.55);
            border-radius: 8px;
            font-size: 11px;
            font-weight: 600;
            padding: 4px 14px;
        }
        QPushButton:hover { background: rgba(110,198,255,0.42); }
    """)
    commit_btn_row.addWidget(commit_go_btn)
    commit_btn_row.addStretch(1)
    cbl.addLayout(commit_btn_row)

    spl.addWidget(commit_box)

    tabs.addTab(status_page, "📊 Статус")

    # ---- Вкладка: Log ----
    log_page = QWidget()
    logl = QVBoxLayout(log_page)
    logl.setContentsMargins(20, 20, 20, 20)
    logl.setSpacing(12)

    log_title = QLabel("История коммитов")
    log_title.setStyleSheet("color: white; font-size: 14px; font-weight: 600;")
    logl.addWidget(log_title)

    log_text = QTextEdit()
    log_text.setReadOnly(True)
    log_text.setStyleSheet(status_text.styleSheet())
    logl.addWidget(log_text, 1)

    tabs.addTab(log_page, "📜 История")

    # ---- Вкладка: Diff ----
    diff_page = QWidget()
    dfl = QVBoxLayout(diff_page)
    dfl.setContentsMargins(20, 20, 20, 20)
    dfl.setSpacing(12)

    diff_title = QLabel("Изменения (git diff)")
    diff_title.setStyleSheet("color: white; font-size: 14px; font-weight: 600;")
    dfl.addWidget(diff_title)

    diff_text = QTextEdit()
    diff_text.setReadOnly(True)
    diff_text.setStyleSheet(status_text.styleSheet())
    dfl.addWidget(diff_text, 1)

    tabs.addTab(diff_page, "🔀 Diff")

    # ---- Вкладка: Console ----
    console_page = QWidget()
    cpl = QVBoxLayout(console_page)
    cpl.setContentsMargins(20, 20, 20, 20)
    cpl.setSpacing(12)

    console_title = QLabel("Git консоль (любая команда)")
    console_title.setStyleSheet("color: white; font-size: 14px; font-weight: 600;")
    cpl.addWidget(console_title)

    console_output = QTextEdit()
    console_output.setReadOnly(True)
    console_output.setStyleSheet(status_text.styleSheet())
    cpl.addWidget(console_output, 1)

    cmd_row = QHBoxLayout()
    cmd_row.setSpacing(8)

    cmd_input = QLineEdit()
    cmd_input.setPlaceholderText("git status  (без префикса git)")
    cmd_input.setStyleSheet(commit_input.styleSheet())
    cmd_row.addWidget(cmd_input, 1)

    run_btn = QPushButton("▶  Run")
    run_btn.setFixedHeight(36)
    run_btn.setCursor(Qt.PointingHandCursor)
    run_btn.setStyleSheet(commit_go_btn.styleSheet())
    cmd_row.addWidget(run_btn)

    cpl.addLayout(cmd_row)

    tabs.addTab(console_page, "💻 Консоль")

    rl.addWidget(tabs, 1)

    h.addWidget(right, 1)

    # ============================================================
    #  Логика
    # ============================================================

    def set_repo_path(path: str):
        st["repo_path"] = path
        path_lbl.setText(f"📁 {os.path.basename(path)}\n{path}")
        if vfs:
            try:
                vfs.mkdir("/Documents")
                vfs.write_text(LAST_REPO_PATH, path)
            except Exception:
                pass
        refresh_all()

    def run_async(*args, on_done=None, timeout=15):
        if not st["repo_path"]:
            return
        worker = GitWorker(st["repo_path"], *args, timeout=timeout)
        st["worker"] = worker

        def callback(ok, out, err):
            if on_done:
                on_done(ok, out, err)

        worker.done.connect(callback)
        worker.start()

    def refresh_status():
        if not st["repo_path"]:
            status_text.setPlainText("Открой репозиторий")
            return

        def on_done(ok, out, err):
            if ok:
                status_text.setPlainText(out or "(чисто)")
            else:
                status_text.setPlainText(f"⚠ Ошибка:\n{err}")

        run_async("status", on_done=on_done)

    def refresh_log():
        if not st["repo_path"]:
            return

        def on_done(ok, out, err):
            if ok:
                log_text.setPlainText(out or "(нет коммитов)")
            else:
                log_text.setPlainText(f"⚠ {err}")

        run_async("log", "--oneline", "--decorate", "-n", "50",
                  on_done=on_done)

    def refresh_diff():
        if not st["repo_path"]:
            return

        def on_done(ok, out, err):
            if ok:
                diff_text.setPlainText(out or "(нет изменений)")
            else:
                diff_text.setPlainText(f"⚠ {err}")

        run_async("diff", on_done=on_done)

    def refresh_branches():
        branches_list.clear()
        if not st["repo_path"]:
            return

        def on_done(ok, out, err):
            if not ok:
                return
            current = ""
            # Определяем текущую
            def on_branch(ok2, out2, err2):
                cur = out2.strip().replace("* ", "") if ok2 else ""
                # Заполняем список
                for line in out.splitlines():
                    name = line.strip().replace("* ", "")
                    if not name:
                        continue
                    is_current = (name == cur)
                    item = QListWidgetItem(
                        ("🌿  " if is_current else "   ") + name)
                    item.setData(Qt.UserRole, name)
                    if is_current:
                        item.setForeground(QColor("#6EC6FF"))
                        font = QFont()
                        font.setBold(True)
                        item.setFont(font)
                    branches_list.addItem(item)
            run_async("branch", on_done=on_branch)

        run_async("branch", "-a", on_done=on_done)

    def refresh_all():
        refresh_status()
        refresh_log()
        refresh_diff()
        refresh_branches()

    def open_repo():
        path = QFileDialog.getExistingDirectory(
            root, "Выбери папку репозитория",
            os.path.expanduser("~"))
        if not path:
            return

        # Проверяем, есть ли .git
        if not os.path.isdir(os.path.join(path, ".git")):
            ans = QMessageBox.question(root, "Git репозиторий",
                "В этой папке нет .git — это не репозиторий.\n\n"
                "Инициализировать новый репозиторий?",
                QMessageBox.Yes | QMessageBox.No)
            if ans != QMessageBox.Yes:
                return
            ok, out, err = run_git(path, "init")
            if not ok:
                QMessageBox.warning(root, "Ошибка", err)
                return

        set_repo_path(path)

    def clone_repo():
        url, ok = QInputDialog.getText(
            root, "Клонировать репозиторий",
            "URL репозитория:\n(например https://github.com/user/repo.git)")
        if not ok or not url.strip():
            return

        # Куда клонировать?
        parent = QFileDialog.getExistingDirectory(
            root, "Куда клонировать?", os.path.expanduser("~"))
        if not parent:
            return

        # Имя папки
        repo_name = url.strip().rstrip("/").split("/")[-1]
        if repo_name.endswith(".git"):
            repo_name = repo_name[:-4]

        target = os.path.join(parent, repo_name)
        if os.path.exists(target):
            QMessageBox.warning(root, "Ошибка",
                f"Папка уже существует:\n{target}")
            return

        # Клонируем асинхронно
        QMessageBox.information(root, "Клонирование",
            f"Клонирую {url}\nв {target}\n\nЭто может занять время…")

        def on_clone_done(ok, out, err):
            if ok:
                set_repo_path(target)
                if desktop and hasattr(desktop, "notifications"):
                    desktop.notifications.push("Git", f"Склонировано: {repo_name}")
            else:
                QMessageBox.warning(root, "Ошибка клонирования", err)

        try:
            worker = GitWorker(parent, "clone", url.strip(), target, timeout=300)
            st["worker"] = worker
            worker.done.connect(on_clone_done)
            worker.start()
        except Exception as e:
            QMessageBox.warning(root, "Ошибка", str(e))

    def stage_all():
        if not st["repo_path"]:
            return
        def on_done(ok, out, err):
            refresh_status()
            refresh_diff()
        run_async("add", ".", on_done=on_done)

    def do_commit():
        if not st["repo_path"]:
            return
        msg = commit_input.text().strip()
        if not msg:
            QMessageBox.information(root, "Commit",
                "Введи сообщение коммита.")
            return

        def on_done(ok, out, err):
            if ok:
                commit_input.clear()
                refresh_all()
                if desktop and hasattr(desktop, "notifications"):
                    desktop.notifications.push("Git", f"Коммит: {msg}")
            else:
                QMessageBox.warning(root, "Ошибка commit", err)

        run_async("commit", "-m", msg, on_done=on_done)

    def do_pull():
        if not st["repo_path"]:
            return
        def on_done(ok, out, err):
            refresh_all()
            if not ok:
                QMessageBox.warning(root, "Ошибка pull", err)
        run_async("pull", on_done=on_done, timeout=60)

    def do_push():
        if not st["repo_path"]:
            return
        def on_done(ok, out, err):
            if not ok:
                QMessageBox.warning(root, "Ошибка push", err)
        run_async("push", on_done=on_done, timeout=60)

    def do_fetch():
        if not st["repo_path"]:
            return
        def on_done(ok, out, err):
            refresh_branches()
            if not ok:
                QMessageBox.warning(root, "Ошибка fetch", err)
        run_async("fetch", on_done=on_done, timeout=60)

    def on_branch_click(item):
        name = item.data(Qt.UserRole)
        if not name:
            return
        # Убираем префикс remote
        if name.startswith("remotes/"):
            name = name.replace("remotes/origin/", "")
        if not name:
            return

        ans = QMessageBox.question(root, "Переключение ветки",
            f"Переключиться на ветку «{name}»?",
            QMessageBox.Yes | QMessageBox.No)
        if ans != QMessageBox.Yes:
            return

        def on_done(ok, out, err):
            if ok:
                refresh_all()
                if desktop and hasattr(desktop, "notifications"):
                    desktop.notifications.push("Git", f"Ветка: {name}")
            else:
                QMessageBox.warning(root, "Ошибка checkout", err)

        run_async("checkout", name, on_done=on_done)

    def new_branch():
        if not st["repo_path"]:
            return
        name, ok = QInputDialog.getText(
            root, "Новая ветка", "Имя ветки:")
        if not ok or not name.strip():
            return

        def on_done(ok2, out, err):
            if ok2:
                refresh_branches()
                if desktop and hasattr(desktop, "notifications"):
                    desktop.notifications.push("Git", f"Ветка создана: {name}")
            else:
                QMessageBox.warning(root, "Ошибка", err)

        run_async("checkout", "-b", name.strip(), on_done=on_done)

    def run_console():
        if not st["repo_path"]:
            return
        cmd = cmd_input.text().strip()
        if not cmd:
            return
        cmd_input.clear()

        console_output.append(f"$ git {cmd}")
        args = cmd.split()

        def on_done(ok, out, err):
            if out:
                console_output.append(out)
            if err:
                console_output.append(f"[stderr] {err}")
            console_output.append(f"[exit code: {'0' if ok else '1'}]\n")

        run_async(*args, on_done=on_done, timeout=30)

    open_btn.clicked.connect(open_repo)
    clone_btn.clicked.connect(clone_repo)
    stage_all_btn.clicked.connect(stage_all)
    commit_go_btn.clicked.connect(do_commit)
    fetch_btn.clicked.connect(do_fetch)
    pull_btn.clicked.connect(do_pull)
    push_btn.clicked.connect(do_push)
    new_branch_btn.clicked.connect(new_branch)
    branches_list.itemClicked.connect(on_branch_click)
    cmd_input.returnPressed.connect(run_console)
    run_btn.clicked.connect(run_console)

    # Автообновление
    auto_timer = QTimer(root)
    auto_timer.setInterval(30000)   # каждые 30 сек
    auto_timer.timeout.connect(refresh_all)
    auto_timer.start()

    # Стартовая инициализация
    if st["repo_path"]:
        path_lbl.setText(f"📁 {os.path.basename(st['repo_path'])}\n{st['repo_path']}")
        refresh_all()
    else:
        status_text.setPlainText("Открой репозиторий или клонируй с GitHub")

    return root