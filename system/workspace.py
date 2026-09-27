"""
MountOS — Виртуальные рабочие столы.

Позволяет создать несколько "рабочих столов", между которыми
можно переключаться. На каждом — свои окна, виджеты, ярлыки.

Возможности:
  • 4 виртуальных стола (можно менять количество)
  • Переключение Ctrl+1..4 или через switcher
  • Плавная анимация перехода
  • Каждый стол помнит свои открытые окна
  • Настройки и обои — общие
  • Сохранение в VFS между запусками

API:
    from system.workspace import workspace
    workspace.count()            # 4
    workspace.current()          # 0
    workspace.current_name()     # "Стол 1"
    workspace.switch(2)          # перейти на 3-й стол
    workspace.next()             # следующий
    workspace.prev()             # предыдущий
    workspace.add_window(win)    # привязать окно к текущему столу
    workspace.remove_window(win) # отвязать
    workspace.windows()          # окна текущего стола
"""

import json
import time

from PySide6.QtCore import QObject, Signal


# ============================================================
#  Менеджер рабочих столов
# ============================================================

class WorkspaceManager(QObject):
    """
    Синглтон-менеджер виртуальных рабочих столов.
    Эмитит switched при смене стола.
    """

    switched = Signal(int)      # новый индекс стола
    windows_changed = Signal()  # список окон текущего стола изменился

    def __init__(self):
        super().__init__()
        self._count = 4
        self._current = 0
        self._vfs = None
        self._connected = False

        # Столы: список словарей, каждый хранит состояние
        # {"windows": [win1, win2], "widget_ids": [...], "shortcut_ids": [...]}
        self._desktops = [self._empty_desktop() for _ in range(self._count)]

        # Подключение к VFS
        self._try_connect()

    def _empty_desktop(self) -> dict:
        """Пустое состояние одного стола."""
        return {
            "windows": [],       # ссылки на GlassWindow
            "widget_ids": [],    # id виджетов рабочего стола
            "shortcut_ids": [],  # id ярлыков
        }

    # ------------------------------------------------------------
    #  VFS
    # ------------------------------------------------------------

    def _try_connect(self):
        if self._connected:
            return
        try:
            from PySide6.QtWidgets import QApplication
            for top in QApplication.topLevelWidgets():
                if hasattr(top, "vfs"):
                    self._vfs = top.vfs
                    self._connected = True
                    break
                ref = getattr(top, "desktop_ref", None)
                if ref is not None and hasattr(ref, "vfs"):
                    self._vfs = ref.vfs
                    self._connected = True
                    break

            if self._connected:
                self.load()
                print(f"[Workspace] VFS подключена, "
                      f"{self._count} столов, текущий: {self._current}")
            else:
                from PySide6.QtCore import QTimer
                QTimer.singleShot(2000, self._try_connect)
        except Exception as e:
            print(f"[Workspace] connect: {e}")

    def set_vfs(self, vfs):
        self._vfs = vfs
        self._connected = True
        self.load()

    def _state_path(self) -> str:
        return "/Notes/workspaces.json"

    def load(self):
        """Загружает метаданные (без окон — они создаются заново)."""
        if self._vfs is None:
            return
        try:
            raw = self._vfs.read_text(self._state_path(), "")
            if not raw.strip():
                return
            data = json.loads(raw)
            self._count = max(1, min(9, data.get("count", 4)))
            self._current = max(0, min(self._count - 1,
                                        data.get("current", 0)))
            # Убеждаемся, что у нас ровно count столов
            while len(self._desktops) < self._count:
                self._desktops.append(self._empty_desktop())
            self._desktops = self._desktops[:self._count]
        except Exception as e:
            print(f"[Workspace] load: {e}")

    def save(self):
        """Сохраняет метаданные (без окон — они не сериализуются)."""
        if self._vfs is None:
            return
        try:
            self._vfs.mkdir("/Notes")
            data = {
                "count": self._count,
                "current": self._current,
            }
            self._vfs.write_text(self._state_path(),
                                 json.dumps(data, ensure_ascii=False, indent=2))
        except Exception as e:
            print(f"[Workspace] save: {e}")

    # ------------------------------------------------------------
    #  Основное API
    # ------------------------------------------------------------

    def count(self) -> int:
        return self._count

    def current(self) -> int:
        return self._current

    def current_name(self) -> str:
        return f"Стол {self._current + 1}"

    def name_for(self, index: int) -> str:
        return f"Стол {index + 1}"

    # ------------------------------------------------------------
    #  Переключение
    # ------------------------------------------------------------

    def switch(self, index: int):
        """Переключиться на стол по индексу."""
        if not 0 <= index < self._count:
            return
        if index == self._current:
            return
        old = self._current
        self._current = index
        self.save()
        self.switched.emit(index)
        print(f"[Workspace] переключение: {old} → {index}")

    def next(self):
        """Следующий стол (по кругу)."""
        self.switch((self._current + 1) % self._count)

    def prev(self):
        """Предыдущий стол (по кругу)."""
        self.switch((self._current - 1) % self._count)

    def set_count(self, n: int):
        """
        Изменить количество столов (1..9).
        Если уменьшаем — окна "лишних" столов переносятся на последний.
        """
        n = max(1, min(9, n))
        if n == self._count:
            return
        if n < self._count:
            # Объединяем окна срезанных столов в последний оставшийся
            last = n - 1
            for i in range(n, self._count):
                for win in self._desktops[i].get("windows", []):
                    self._desktops[last]["windows"].append(win)
            self._desktops = self._desktops[:n]
            if self._current >= n:
                self._current = n - 1
                self.switched.emit(self._current)
        else:
            # Добавляем пустые
            while len(self._desktops) < n:
                self._desktops.append(self._empty_desktop())
        self._count = n
        self.save()
        self.windows_changed.emit()

    # ------------------------------------------------------------
    #  Окна
    # ------------------------------------------------------------

    def windows(self):
        """Окна текущего стола."""
        return list(self._desktops[self._current]["windows"])

    def windows_of(self, index: int):
        """Окна указанного стола."""
        if 0 <= index < self._count:
            return list(self._desktops[index]["windows"])
        return []

    def all_windows(self):
        """Все окна всех столов."""
        result = []
        for d in self._desktops:
            result.extend(d["windows"])
        return result

    def add_window(self, win):
        """Привязать окно к текущему столу."""
        d = self._desktops[self._current]
        if win not in d["windows"]:
            d["windows"].append(win)
            self.windows_changed.emit()

    def remove_window(self, win):
        """Отвязать окно от всех столов."""
        removed = False
        for d in self._desktops:
            if win in d["windows"]:
                d["windows"].remove(win)
                removed = True
        if removed:
            self.windows_changed.emit()

    def is_visible(self, win) -> bool:
        """Видно ли окно на текущем столе."""
        return win in self._desktops[self._current]["windows"]

    # ------------------------------------------------------------
    #  Виджеты рабочего стола
    # ------------------------------------------------------------

    def add_widget_id(self, widget_id: str):
        d = self._desktops[self._current]
        if widget_id not in d["widget_ids"]:
            d["widget_ids"].append(widget_id)
            self.windows_changed.emit()

    def remove_widget_id(self, widget_id: str):
        for d in self._desktops:
            if widget_id in d["widget_ids"]:
                d["widget_ids"].remove(widget_id)
        self.windows_changed.emit()

    def widget_ids(self):
        return list(self._desktops[self._current]["widget_ids"])

    # ------------------------------------------------------------
    #  Ярлыки
    # ------------------------------------------------------------

    def add_shortcut_id(self, sid: str):
        d = self._desktops[self._current]
        if sid not in d["shortcut_ids"]:
            d["shortcut_ids"].append(sid)
            self.windows_changed.emit()

    def remove_shortcut_id(self, sid: str):
        for d in self._desktops:
            if sid in d["shortcut_ids"]:
                d["shortcut_ids"].remove(sid)
        self.windows_changed.emit()

    def shortcut_ids(self):
        return list(self._desktops[self._current]["shortcut_ids"])

    # ------------------------------------------------------------
    #  Статистика
    # ------------------------------------------------------------

    def summary(self):
        """Сводка по всем столам: [{index, name, windows_count}, ...]"""
        return [
            {
                "index": i,
                "name": self.name_for(i),
                "windows_count": len(self._desktops[i]["windows"]),
            }
            for i in range(self._count)
        ]

    def window_count_of(self, index: int) -> int:
        if 0 <= index < self._count:
            return len(self._desktops[index]["windows"])
        return 0


# ============================================================
#  Синглтон
# ============================================================

_workspace_instance = None


def workspace() -> WorkspaceManager:
    """Возвращает глобальный менеджер рабочих столов."""
    global _workspace_instance
    if _workspace_instance is None:
        _workspace_instance = WorkspaceManager()
    return _workspace_instance