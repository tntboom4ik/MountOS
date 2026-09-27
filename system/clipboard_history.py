"""
MountOS — История буфера обмена.

Отслеживает всё, что копируется в MountOS, и сохраняет
историю (по умолчанию 50 элементов).

Возможности:
  • Автоматический перехват Ctrl+C / Ctrl+X
  • История текста (позже — можно картинки)
  • Поиск по истории
  • Закрепление важных элементов
  • Автоочистка старых
  • Сохранение между запусками в VFS

Использование:
    from system.clipboard_history import clipboard
    clipboard.add("текст")
    clipboard.items()           # список всех элементов
    clipboard.search("привет")  # поиск
    clipboard.copy_back(0)      # вернуть 0-й элемент в буфер
    clipboard.clear()           # очистить
"""

import json
import time
from datetime import datetime

from PySide6.QtCore import QObject, Signal, QTimer
from PySide6.QtWidgets import QApplication


MAX_ITEMS = 50       # максимум элементов в истории
MAX_AGE_DAYS = 7     # автоудаление старше 7 дней


# ============================================================
#  Модель одного элемента
# ============================================================

class ClipboardItem:
    def __init__(self, text: str, kind: str = "text",
                 pinned: bool = False, source: str = ""):
        self.text = text
        self.kind = kind            # "text" | "image" (пока только text)
        self.pinned = pinned        # закреплён ли
        self.source = source        # откуда скопировано (имя приложения)
        self.timestamp = time.time()

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "kind": self.kind,
            "pinned": self.pinned,
            "source": self.source,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, d: dict):
        item = cls(d.get("text", ""),
                   kind=d.get("kind", "text"),
                   pinned=d.get("pinned", False),
                   source=d.get("source", ""))
        item.timestamp = d.get("timestamp", time.time())
        return item

    def preview(self, max_len: int = 60) -> str:
        """Однострочное превью для UI."""
        text = self.text.replace("\n", " ").replace("\r", " ").strip()
        if len(text) > max_len:
            text = text[:max_len - 1] + "…"
        return text

    def time_ago(self) -> str:
        """Человекочитаемое время."""
        diff = time.time() - self.timestamp
        if diff < 60:
            return "только что"
        if diff < 3600:
            return f"{int(diff // 60)} мин назад"
        if diff < 86400:
            return f"{int(diff // 3600)} ч назад"
        if diff < 86400 * 7:
            return f"{int(diff // 86400)} дн назад"
        dt = datetime.fromtimestamp(self.timestamp)
        return dt.strftime("%d.%m %H:%M")


# ============================================================
#  Менеджер буфера
# ============================================================

class ClipboardHistory(QObject):
    """
    Синглтон-менеджер истории буфера обмена.
    Эмитит сигналы при добавлении/удалении.
    """

    added = Signal()      # добавлен новый элемент
    changed = Signal()    # любое изменение
    cleared = Signal()    # история очищена

    def __init__(self):
        super().__init__()
        self._items = []
        self._vfs = None
        self._last_text = ""    # чтобы не дублировать
        self._connected = False

        # Таймер для отслеживания системного буфера
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(800)   # раз в 0.8 сек
        self._poll_timer.timeout.connect(self._poll_clipboard)

        # Пробуем подключиться к VFS и загрузить
        self._try_connect()

    # ------------------------------------------------------------
    #  Подключение к VFS
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
                self._poll_timer.start()
                print(f"[Clipboard] подключён к VFS, "
                      f"{len(self._items)} элементов в истории")
            else:
                # Повторим через 2 сек
                QTimer.singleShot(2000, self._try_connect)
        except Exception as e:
            print(f"[Clipboard] connect: {e}")
            QTimer.singleShot(2000, self._try_connect)

    def set_vfs(self, vfs):
        """Установить VFS вручную (если вызовут)."""
        self._vfs = vfs
        self._connected = True
        self.load()
        if not self._poll_timer.isActive():
            self._poll_timer.start()

    # ------------------------------------------------------------
    #  Файл истории
    # ------------------------------------------------------------

    def _history_path(self) -> str:
        return "/Notes/clipboard_history.json"

    def load(self):
        """Загрузить историю из VFS."""
        if self._vfs is None:
            return
        try:
            raw = self._vfs.read_text(self._history_path(), "")
            if not raw.strip():
                self._items = []
                return
            data = json.loads(raw)
            if isinstance(data, list):
                self._items = [ClipboardItem.from_dict(d) for d in data]
                self._cleanup_old()
        except Exception as e:
            print(f"[Clipboard] load: {e}")
            self._items = []

    def save(self):
        """Сохранить историю в VFS."""
        if self._vfs is None:
            return
        try:
            self._vfs.mkdir("/Notes")
            data = [it.to_dict() for it in self._items]
            self._vfs.write_text(
                self._history_path(),
                json.dumps(data, ensure_ascii=False, indent=2))
        except Exception as e:
            print(f"[Clipboard] save: {e}")

    # ------------------------------------------------------------
    #  Отслеживание системного буфера
    # ------------------------------------------------------------

    def _poll_clipboard(self):
        """Проверяет системный буфер и добавляет изменения."""
        try:
            cb = QApplication.clipboard()
            text = cb.text()
            if text and text != self._last_text:
                self._last_text = text
                # Не добавляем пустые/огромные
                if len(text) > 100_000:
                    return
                self.add(text, source="system")
        except Exception:
            pass

    # ------------------------------------------------------------
    #  Добавление
    # ------------------------------------------------------------

    def add(self, text: str, kind: str = "text", source: str = ""):
        """
        Добавляет текст в историю.
        Если такой уже есть (в начале) — переносит его наверх.
        """
        if not text or not text.strip():
            return

        # Если последний элемент совпадает — обновим timestamp
        if self._items and self._items[0].text == text:
            self._items[0].timestamp = time.time()
            self.save()
            return

        # Удаляем дубликат (если такой уже был)
        self._items = [it for it in self._items if it.text != text]

        # Создаём новый элемент
        item = ClipboardItem(text, kind=kind, source=source)
        self._items.insert(0, item)

        # Ограничение по количеству
        self._trim()

        self.save()
        self.added.emit()
        self.changed.emit()

    def _trim(self):
        """Убирает лишние элементы, сохраняя закреплённые."""
        # Считаем закреплённые
        pinned = [it for it in self._items if it.pinned]
        unpinned = [it for it in self._items if not it.pinned]

        # Ограничиваем по общему количеству
        max_total = MAX_ITEMS
        max_unpinned = max_total - len(pinned)
        if max_unpinned < 0:
            max_unpinned = 0
        unpinned = unpinned[:max_unpinned]

        # Восстанавливаем порядок (по timestamp, свежие сверху)
        all_items = pinned + unpinned
        all_items.sort(key=lambda it: (-it.pinned, -it.timestamp))
        self._items = all_items

    def _cleanup_old(self):
        """Удаляет элементы старше MAX_AGE_DAYS (кроме закреплённых)."""
        now = time.time()
        cutoff = now - MAX_AGE_DAYS * 86400
        self._items = [
            it for it in self._items
            if it.pinned or it.timestamp > cutoff
        ]

    # ------------------------------------------------------------
    #  Чтение
    # ------------------------------------------------------------

    def items(self):
        """Все элементы истории (свежие сверху)."""
        return list(self._items)

    def count(self) -> int:
        return len(self._items)

    def pinned(self):
        return [it for it in self._items if it.pinned]

    def get(self, index: int):
        """Получить элемент по индексу."""
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def search(self, query: str):
        """Поиск по тексту (без учёта регистра)."""
        if not query:
            return list(self._items)
        q = query.lower()
        return [it for it in self._items if q in it.text.lower()]

    # ------------------------------------------------------------
    #  Действия
    # ------------------------------------------------------------

    def copy_back(self, index: int) -> bool:
        """Копирует элемент обратно в системный буфер."""
        item = self.get(index)
        if item is None:
            return False
        try:
            cb = QApplication.clipboard()
            cb.setText(item.text)
            # Обновляем _last_text, чтобы не добавить себя же снова
            self._last_text = item.text
            # Переносим элемент наверх
            self._items.remove(item)
            item.timestamp = time.time()
            self._items.insert(0, item)
            self.save()
            self.changed.emit()
            return True
        except Exception as e:
            print(f"[Clipboard] copy_back: {e}")
            return False

    def toggle_pin(self, index: int):
        """Закрепить/открепить элемент."""
        item = self.get(index)
        if item is None:
            return
        item.pinned = not item.pinned
        # Пересортируем: закреплённые наверху
        self._items.sort(key=lambda it: (-it.pinned, -it.timestamp))
        self.save()
        self.changed.emit()

    def remove(self, index: int):
        """Удалить элемент."""
        if 0 <= index < len(self._items):
            del self._items[index]
            self.save()
            self.changed.emit()

    def clear(self, keep_pinned: bool = True):
        """
        Очистить историю.
        keep_pinned=True — закреплённые остаются.
        """
        if keep_pinned:
            self._items = [it for it in self._items if it.pinned]
        else:
            self._items = []
        self.save()
        self.cleared.emit()
        self.changed.emit()

    def clear_old(self, days: int = 1):
        """Удалить элементы старше N дней (кроме закреплённых)."""
        cutoff = time.time() - days * 86400
        before = len(self._items)
        self._items = [
            it for it in self._items
            if it.pinned or it.timestamp > cutoff
        ]
        removed = before - len(self._items)
        if removed > 0:
            self.save()
            self.changed.emit()
        return removed

    # ------------------------------------------------------------
    #  Статистика
    # ------------------------------------------------------------

    def stats(self) -> dict:
        """Статистика истории."""
        total = len(self._items)
        pinned = sum(1 for it in self._items if it.pinned)
        total_chars = sum(len(it.text) for it in self._items)
        return {
            "total": total,
            "pinned": pinned,
            "total_chars": total_chars,
        }


# ============================================================
#  Синглтон
# ============================================================

_clipboard_instance = None


def clipboard() -> ClipboardHistory:
    """Возвращает глобальный менеджер буфера обмена."""
    global _clipboard_instance
    if _clipboard_instance is None:
        _clipboard_instance = ClipboardHistory()
    return _clipboard_instance