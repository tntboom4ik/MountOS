"""
MountOS — Корзина.

Удалённые файлы не стираются сразу, а попадают в корзину.
Их можно восстановить или стереть окончательно.

Возможности:
  • Перемещение в корзину вместо удаления
  • Восстановление в исходное место
  • Окончательное удаление
  • Автоочистка через N дней (по умолчанию 30)
  • Ограничение по размеру (по умолчанию 500 МБ)
  • Сохранение метаданных (когда и откуда удалён)
  • Пустая корзина
  • Статистика

Структура:
  /Trash/                              — корень корзины
  /Trash/files/                        — сами файлы
  /Trash/metadata.json                 — метаданные (откуда, когда)

API:
    from system.trash import TrashManager
    trash = TrashManager(vfs)
    trash.move_to_trash("/Documents/ненужное.txt")
    trash.items()                        # список элементов
    trash.restore(item_id)               # восстановить
    trash.delete_forever(item_id)        # стереть окончательно
    trash.empty()                        # очистить всё
    trash.auto_cleanup()                 # автоочистка старых
"""

import json
import os
import time
from datetime import datetime, timedelta

from PySide6.QtCore import QObject, Signal


# ============================================================
#  Константы
# ============================================================

TRASH_DIR = "/Trash"
FILES_DIR = "/Trash/files"
META_PATH = "/Trash/metadata.json"

DEFAULT_MAX_AGE_DAYS = 30       # автоудаление старше 30 дней
DEFAULT_MAX_SIZE_MB = 500       # максимум 500 МБ


# ============================================================
#  Менеджер корзины
# ============================================================

class TrashManager(QObject):
    """
    Корзина MountOS.
    Работает через VFS — реальный диск не тронут.
    """

    changed = Signal()          # содержимое изменилось
    file_trashed = Signal(str)  # файл отправлен в корзину
    file_restored = Signal(str) # файл восстановлен

    def __init__(self, vfs):
        super().__init__()
        self.vfs = vfs
        self._ensure_structure()
        self.auto_cleanup()

    # ------------------------------------------------------------
    #  Инициализация
    # ------------------------------------------------------------

    def _ensure_structure(self):
        """Создаёт папки и файл метаданных."""
        if self.vfs is None:
            return
        try:
            self.vfs.mkdir(TRASH_DIR)
            self.vfs.mkdir(FILES_DIR)
            if not self.vfs.exists(META_PATH):
                self.vfs.write_text(META_PATH, "[]")
        except Exception as e:
            print(f"[Trash] ensure structure: {e}")

    # ------------------------------------------------------------
    #  Метаданные
    # ------------------------------------------------------------

    def _load_meta(self) -> list:
        if self.vfs is None:
            return []
        try:
            raw = self.vfs.read_text(META_PATH, "[]")
            if not raw.strip():
                return []
            data = json.loads(raw)
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _save_meta(self, data: list):
        if self.vfs is None:
            return
        try:
            self.vfs.write_text(
                META_PATH,
                json.dumps(data, ensure_ascii=False, indent=2))
        except Exception as e:
            print(f"[Trash] save meta: {e}")

    def _next_id(self, meta: list) -> int:
        if not meta:
            return 1
        return max((it.get("id", 0) for it in meta), default=0) + 1

    # ------------------------------------------------------------
    #  Уникальное имя в корзине
    # ------------------------------------------------------------

    def _unique_trash_name(self, original_name: str) -> str:
        """Избегает коллизий имён внутри /Trash/files/."""
        base, dot, ext = original_name.partition(".")
        if not dot:
            ext = ""
        name = f"{base}.{ext}" if ext else base
        candidate = f"{FILES_DIR}/{name}"
        n = 1
        while self.vfs.exists(candidate):
            if ext:
                candidate = f"{FILES_DIR}/{base}_{n}.{ext}"
            else:
                candidate = f"{FILES_DIR}/{base}_{n}"
            n += 1
        return candidate

    # ------------------------------------------------------------
    #  Отправка в корзину
    # ------------------------------------------------------------

    def move_to_trash(self, vfs_path: str) -> tuple:
        """
        Перемещает файл/папку в корзину.
        Возвращает (success, message).
        """
        if self.vfs is None:
            return False, "VFS недоступна"

        if not self.vfs.exists(vfs_path):
            return False, "Файл не найден"

        if vfs_path.startswith(TRASH_DIR):
            return False, "Файл уже в корзине"

        try:
            name = self.vfs.basename(vfs_path)
            trash_path = self._unique_trash_name(name)
            is_dir = self.vfs.is_dir(vfs_path)

            # Копируем в корзину
            self.vfs.copy(vfs_path, trash_path)

            # Удаляем оригинал
            self.vfs.delete(vfs_path)

            # Записываем метаданные
            meta = self._load_meta()
            entry = {
                "id": self._next_id(meta),
                "original_path": vfs_path,
                "trash_path": trash_path,
                "name": name,
                "is_dir": is_dir,
                "size": self._size_of(trash_path),
                "deleted_at": time.time(),
            }
            meta.append(entry)
            self._save_meta(meta)

            self.file_trashed.emit(vfs_path)
            self.changed.emit()
            return True, f"В корзину: {name}"
        except Exception as e:
            return False, f"Ошибка: {e}"

    def _size_of(self, vfs_path: str) -> int:
        """Считает размер файла или папки."""
        if not self.vfs.exists(vfs_path):
            return 0
        if not self.vfs.is_dir(vfs_path):
            try:
                items = self.vfs.listdir(self.vfs.parent(vfs_path))
                for it in items:
                    if it["path"] == vfs_path:
                        return it["size"]
            except Exception:
                return 0
            return 0

        # Папка — считаем рекурсивно
        total = 0
        try:
            for it in self.vfs.listdir(vfs_path):
                if it["is_dir"]:
                    total += self._size_of(it["path"])
                else:
                    total += it["size"]
        except Exception:
            pass
        return total

    # ------------------------------------------------------------
    #  Чтение
    # ------------------------------------------------------------

    def items(self) -> list:
        """
        Возвращает список элементов корзины.
        Свежие сверху.
        """
        meta = self._load_meta()
        # Сортируем по времени удаления (свежие сверху)
        meta.sort(key=lambda it: it.get("deleted_at", 0), reverse=True)
        return meta

    def count(self) -> int:
        return len(self._load_meta())

    def total_size(self) -> int:
        meta = self._load_meta()
        return sum(it.get("size", 0) for it in meta)

    def get(self, item_id: int):
        for it in self._load_meta():
            if it.get("id") == item_id:
                return it
        return None

    def is_empty(self) -> bool:
        return self.count() == 0

    def stats(self) -> dict:
        meta = self._load_meta()
        return {
            "count": len(meta),
            "total_size": sum(it.get("size", 0) for it in meta),
            "oldest": min((it.get("deleted_at", 0) for it in meta), default=0),
            "newest": max((it.get("deleted_at", 0) for it in meta), default=0),
        }

    # ------------------------------------------------------------
    #  Восстановление
    # ------------------------------------------------------------

    def restore(self, item_id: int) -> tuple:
        """
        Восстанавливает элемент в исходное место.
        Если оригинальное место занято — добавляет _1, _2 и т.д.
        """
        meta = self._load_meta()
        item = None
        for it in meta:
            if it.get("id") == item_id:
                item = it
                break

        if item is None:
            return False, "Элемент не найден"

        trash_path = item["trash_path"]
        original = item["original_path"]

        if not self.vfs.exists(trash_path):
            # Файл уже кто-то удалил из корзины
            meta = [it for it in meta if it.get("id") != item_id]
            self._save_meta(meta)
            self.changed.emit()
            return False, "Файла нет в корзине"

        # Проверяем, свободно ли исходное место
        target = original
        if self.vfs.exists(target):
            # Ищем свободное имя
            parent = self.vfs.parent(original)
            name = self.vfs.basename(original)
            base, dot, ext = name.partition(".")
            n = 1
            while self.vfs.exists(target):
                if ext:
                    target = self.vfs.join(parent, f"{base}_{n}.{ext}")
                else:
                    target = self.vfs.join(parent, f"{base}_{n}")
                n += 1

        try:
            # Создаём родительскую папку если нужно
            parent = self.vfs.parent(target)
            if parent and parent != "/" and not self.vfs.exists(parent):
                self.vfs.mkdir(parent)

            # Копируем из корзины в оригинал
            self.vfs.copy(trash_path, target)
            # Удаляем из корзины
            self.vfs.delete(trash_path)

            # Убираем из метаданных
            meta = [it for it in meta if it.get("id") != item_id]
            self._save_meta(meta)

            self.file_restored.emit(target)
            self.changed.emit()
            return True, f"Восстановлено: {target}"
        except Exception as e:
            return False, f"Ошибка восстановления: {e}"

    # ------------------------------------------------------------
    #  Окончательное удаление
    # ------------------------------------------------------------

    def delete_forever(self, item_id: int) -> tuple:
        """Удаляет элемент из корзины навсегда."""
        meta = self._load_meta()
        item = None
        for it in meta:
            if it.get("id") == item_id:
                item = it
                break

        if item is None:
            return False, "Элемент не найден"

        trash_path = item["trash_path"]
        try:
            if self.vfs.exists(trash_path):
                self.vfs.delete(trash_path)
            meta = [it for it in meta if it.get("id") != item_id]
            self._save_meta(meta)
            self.changed.emit()
            return True, f"Удалено: {item['name']}"
        except Exception as e:
            return False, f"Ошибка: {e}"

    def empty(self) -> tuple:
        """Полностью очищает корзину."""
        try:
            if self.vfs.exists(FILES_DIR):
                self.vfs.delete(FILES_DIR)
            self.vfs.mkdir(FILES_DIR)
            self._save_meta([])
            self.changed.emit()
            return True, "Корзина очищена"
        except Exception as e:
            return False, f"Ошибка очистки: {e}"

    # ------------------------------------------------------------
    #  Автоочистка
    # ------------------------------------------------------------

    def auto_cleanup(self, max_age_days: int = DEFAULT_MAX_AGE_DAYS,
                     max_size_mb: int = DEFAULT_MAX_SIZE_MB) -> int:
        """
        Удаляет старые и лишние элементы.
        Возвращает количество удалённых.
        """
        meta = self._load_meta()
        if not meta:
            return 0

        now = time.time()
        cutoff = now - max_age_days * 86400
        removed = 0

        # 1. По возрасту
        keep = []
        for it in meta:
            if it.get("deleted_at", 0) < cutoff:
                # Удаляем файл
                try:
                    if self.vfs.exists(it["trash_path"]):
                        self.vfs.delete(it["trash_path"])
                    removed += 1
                except Exception as e:
                    print(f"[Trash] cleanup old: {e}")
                    keep.append(it)
            else:
                keep.append(it)

        # 2. По размеру
        max_bytes = max_size_mb * 1024 * 1024
        current = sum(it.get("size", 0) for it in keep)
        # Сортируем: самые старые первыми
        keep.sort(key=lambda it: it.get("deleted_at", 0))

        while current > max_bytes and keep:
            oldest = keep.pop(0)
            try:
                if self.vfs.exists(oldest["trash_path"]):
                    self.vfs.delete(oldest["trash_path"])
                current -= oldest.get("size", 0)
                removed += 1
            except Exception as e:
                print(f"[Trash] cleanup size: {e}")

        if removed > 0:
            self._save_meta(keep)
            self.changed.emit()
            print(f"[Trash] автоочистка: удалено {removed} элементов")

        return removed

    # ------------------------------------------------------------
    #  Утилиты
    # ------------------------------------------------------------

    @staticmethod
    def human_size(n: int) -> str:
        if n < 0:
            return "—"
        units = ["Б", "КБ", "МБ", "ГБ"]
        f = float(n)
        for u in units:
            if f < 1024:
                return f"{f:.1f} {u}"
            f /= 1024
        return f"{f:.1f} ТБ"

    @staticmethod
    def time_ago(ts: float) -> str:
        if not ts:
            return "—"
        diff = time.time() - ts
        if diff < 60:
            return "только что"
        if diff < 3600:
            return f"{int(diff // 60)} мин назад"
        if diff < 86400:
            return f"{int(diff // 3600)} ч назад"
        if diff < 86400 * 30:
            return f"{int(diff // 86400)} дн назад"
        dt = datetime.fromtimestamp(ts)
        return dt.strftime("%d.%m.%Y %H:%M")