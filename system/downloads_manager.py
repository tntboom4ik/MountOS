"""
MountOS — Менеджер загрузок.

Единая система для всех скачанных файлов:
  • История загрузок (из браузера и других источников)
  • Прогресс в реальном времени
  • Пауза / продолжение / отмена
  • Открытие файла / папки / удаление
  • Статистика (всего скачано, размер, скорость)
  • Сохранение метаданных в VFS

API:
    from system.downloads_manager import downloads
    downloads.add(url, path, name)
    downloads.list()
    downloads.get(id)
    downloads.remove(id)
    downloads.clear_finished()
    downloads.stats()
"""

import json
import os
import time
from datetime import datetime

from PySide6.QtCore import QObject, Signal, QTimer


# ============================================================
#  Константы
# ============================================================

META_PATH = "/Downloads/.downloads.json"
MAX_HISTORY = 200    # хранить не больше 200 записей


# ============================================================
#  Статусы
# ============================================================

STATUS_ACTIVE = "active"          # качается прямо сейчас
STATUS_PAUSED = "paused"          # на паузе
STATUS_DONE = "done"              # завершено
STATUS_ERROR = "error"            # ошибка
STATUS_CANCELLED = "cancelled"    # отменено пользователем


# ============================================================
#  Менеджер
# ============================================================

class DownloadsManager(QObject):
    """
    Синглтон-менеджер загрузок MountOS.
    """

    added = Signal(int)          # id новой загрузки
    updated = Signal(int)        # id обновлённой загрузки
    removed = Signal(int)        # id удалённой записи
    changed = Signal()           # любое изменение в списке
    finished = Signal(int, str)  # id, path — загрузка завершена

    def __init__(self):
        super().__init__()
        self._items = []
        self._next_id = 1
        self._vfs = None
        self._connected = False

        # Периодическое сохранение
        self._save_timer = QTimer(self)
        self._save_timer.setInterval(5000)  # каждые 5 сек
        self._save_timer.timeout.connect(self.save)

        self._try_connect()

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
                self._save_timer.start()
                print(f"[Downloads] VFS подключена, "
                      f"{len(self._items)} записей")
            else:
                QTimer.singleShot(2000, self._try_connect)
        except Exception as e:
            print(f"[Downloads] connect: {e}")
            QTimer.singleShot(2000, self._try_connect)

    def set_vfs(self, vfs):
        self._vfs = vfs
        self._connected = True
        self.load()
        if not self._save_timer.isActive():
            self._save_timer.start()

    # ------------------------------------------------------------
    #  Загрузка / сохранение
    # ------------------------------------------------------------

    def load(self):
        if self._vfs is None:
            return
        try:
            raw = self._vfs.read_text(META_PATH, "")
            if not raw.strip():
                self._items = []
                return
            data = json.loads(raw)
            if isinstance(data, dict):
                self._items = data.get("items", [])
                self._next_id = data.get("next_id", 1)
            elif isinstance(data, list):
                self._items = data
                self._next_id = max((it.get("id", 0) for it in data),
                                     default=0) + 1

            # Помечаем "активные" как прерванные (MountOS перезапущена)
            for it in self._items:
                if it.get("status") == STATUS_ACTIVE:
                    it["status"] = STATUS_ERROR
                    it["error"] = "MountOS была перезапущена"
        except Exception as e:
            print(f"[Downloads] load: {e}")
            self._items = []

    def save(self):
        if self._vfs is None:
            return
        try:
            self._vfs.mkdir("/Downloads")
            data = {
                "items": self._items[-MAX_HISTORY:],
                "next_id": self._next_id,
            }
            self._vfs.write_text(
                META_PATH,
                json.dumps(data, ensure_ascii=False, indent=2))
        except Exception as e:
            print(f"[Downloads] save: {e}")

    # ------------------------------------------------------------
    #  Добавление
    # ------------------------------------------------------------

    def add(self, url: str, path: str = "", name: str = "",
            size: int = 0) -> int:
        """
        Добавляет новую запись о загрузке.
        Возвращает id.
        """
        if not name:
            name = url.split("/")[-1].split("?")[0] or "файл"

        item = {
            "id": self._next_id,
            "url": url,
            "path": path,
            "name": name,
            "size": size,
            "downloaded": 0,
            "status": STATUS_ACTIVE,
            "started_at": time.time(),
            "finished_at": 0,
            "error": "",
        }
        self._next_id += 1
        self._items.append(item)

        self.save()
        self.added.emit(item["id"])
        self.changed.emit()
        return item["id"]

    # ------------------------------------------------------------
    #  Обновление
    # ------------------------------------------------------------

    def update_progress(self, item_id: int, downloaded: int,
                        total: int = None):
        """Обновляет прогресс загрузки."""
        item = self.get(item_id)
        if item is None:
            return
        item["downloaded"] = downloaded
        if total is not None:
            item["size"] = total
        self.updated.emit(item_id)
        self.changed.emit()

    def mark_done(self, item_id: int):
        """Помечает как завершённую."""
        item = self.get(item_id)
        if item is None:
            return
        item["status"] = STATUS_DONE
        item["finished_at"] = time.time()
        if item["size"] == 0 and item["path"] and self._vfs:
            item["size"] = self._actual_size(item["path"])
        self.updated.emit(item_id)
        self.changed.emit()
        self.finished.emit(item_id, item.get("path", ""))

    def mark_error(self, item_id: int, error: str):
        item = self.get(item_id)
        if item is None:
            return
        item["status"] = STATUS_ERROR
        item["error"] = error
        self.updated.emit(item_id)
        self.changed.emit()

    def mark_paused(self, item_id: int):
        item = self.get(item_id)
        if item is None:
            return
        item["status"] = STATUS_PAUSED
        self.updated.emit(item_id)
        self.changed.emit()

    def mark_cancelled(self, item_id: int):
        item = self.get(item_id)
        if item is None:
            return
        item["status"] = STATUS_CANCELLED
        self.updated.emit(item_id)
        self.changed.emit()

    # ------------------------------------------------------------
    #  Чтение
    # ------------------------------------------------------------

    def list(self) -> list:
        """Все записи, свежие сверху."""
        return list(reversed(self._items))

    def get(self, item_id: int):
        for it in self._items:
            if it.get("id") == item_id:
                return it
        return None

    def active(self) -> list:
        return [it for it in self._items
                if it.get("status") == STATUS_ACTIVE]

    def finished(self) -> list:
        return [it for it in self._items
                if it.get("status") == STATUS_DONE]

    def errors(self) -> list:
        return [it for it in self._items
                if it.get("status") == STATUS_ERROR]

    def count(self) -> int:
        return len(self._items)

    def has_active(self) -> bool:
        return any(it.get("status") == STATUS_ACTIVE
                   for it in self._items)

    # ------------------------------------------------------------
    #  Удаление
    # ------------------------------------------------------------

    def remove(self, item_id: int, delete_file: bool = False):
        """Удаляет запись (и, опционально, файл)."""
        item = self.get(item_id)
        if item is None:
            return False
        if delete_file and item.get("path") and self._vfs:
            try:
                if self._vfs.exists(item["path"]):
                    self._vfs.delete(item["path"])
            except Exception as e:
                print(f"[Downloads] delete file: {e}")
        self._items = [it for it in self._items if it.get("id") != item_id]
        self.save()
        self.removed.emit(item_id)
        self.changed.emit()
        return True

    def clear_finished(self, delete_files: bool = False):
        """Очищает завершённые записи."""
        to_remove = [it["id"] for it in self._items
                     if it.get("status") in (STATUS_DONE,
                                              STATUS_CANCELLED,
                                              STATUS_ERROR)]
        for rid in to_remove:
            self.remove(rid, delete_file=delete_files)
        return len(to_remove)

    def clear_all(self, delete_files: bool = False):
        """Очищает всю историю."""
        if delete_files and self._vfs:
            for it in self._items:
                try:
                    p = it.get("path", "")
                    if p and self._vfs.exists(p):
                        self._vfs.delete(p)
                except Exception:
                    pass
        self._items = []
        self.save()
        self.changed.emit()

    # ------------------------------------------------------------
    #  Статистика
    # ------------------------------------------------------------

    def stats(self) -> dict:
        total = len(self._items)
        done = sum(1 for it in self._items
                   if it.get("status") == STATUS_DONE)
        active = sum(1 for it in self._items
                     if it.get("status") == STATUS_ACTIVE)
        errors = sum(1 for it in self._items
                     if it.get("status") == STATUS_ERROR)
        total_size = sum(it.get("size", 0) for it in self._items
                         if it.get("status") == STATUS_DONE)
        return {
            "total": total,
            "done": done,
            "active": active,
            "errors": errors,
            "total_size": total_size,
        }

    # ------------------------------------------------------------
    #  Утилиты
    # ------------------------------------------------------------

    def _actual_size(self, vfs_path: str) -> int:
        """Реальный размер файла в VFS."""
        if self._vfs is None or not self._vfs.exists(vfs_path):
            return 0
        try:
            data = self._vfs.read_bytes(vfs_path)
            return len(data)
        except Exception:
            return 0

    @staticmethod
    def fmt_size(n: int) -> str:
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
    def fmt_speed(bps: float) -> str:
        return DownloadsManager.fmt_size(int(bps)) + "/с"

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
        dt = datetime.fromtimestamp(ts)
        return dt.strftime("%d.%m %H:%M")

    def progress_percent(self, item_id: int) -> int:
        """Прогресс в процентах (0..100)."""
        it = self.get(item_id)
        if it is None:
            return 0
        size = it.get("size", 0)
        done = it.get("downloaded", 0)
        if size <= 0:
            return 100 if it.get("status") == STATUS_DONE else 0
        return min(100, int(done / size * 100))

    def current_speed(self, item_id: int) -> float:
        """Приблизительная скорость (байт/сек)."""
        it = self.get(item_id)
        if it is None:
            return 0.0
        if it.get("status") != STATUS_ACTIVE:
            return 0.0
        elapsed = time.time() - it.get("started_at", time.time())
        if elapsed <= 0:
            return 0.0
        return it.get("downloaded", 0) / elapsed

    # ------------------------------------------------------------
    #  Скачивание через requests (для прямых URL)
    # ------------------------------------------------------------

    def download_url(self, url: str, dest_dir: str = "/Downloads",
                      custom_name: str = "") -> tuple:
        """
        Скачивает файл по URL прямо в VFS.
        Возвращает (success, message).
        Работает синхронно — для больших файлов лучше делать в потоке.
        """
        try:
            import urllib.request
            import urllib.error
        except ImportError:
            return False, "urllib недоступен"

        name = custom_name or url.split("/")[-1].split("?")[0] or "файл"
        target = self._vfs.join(dest_dir, name) if self._vfs else f"{dest_dir}/{name}"

        # Проверяем коллизию
        if self._vfs and self._vfs.exists(target):
            base, dot, ext = name.partition(".")
            n = 1
            while self._vfs.exists(target):
                target = self._vfs.join(dest_dir,
                                        f"{base}_{n}{dot}{ext}")
                n += 1

        item_id = self.add(url, target, name)

        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent":
                         "Mozilla/5.0 MountOS/1.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                total = int(resp.headers.get("Content-Length", 0))
                chunks = []
                downloaded = 0
                while True:
                    chunk = resp.read(64 * 1024)
                    if not chunk:
                        break
                    chunks.append(chunk)
                    downloaded += len(chunk)
                    self.update_progress(item_id, downloaded, total)
                data = b"".join(chunks)

            if self._vfs:
                self._vfs.mkdir(dest_dir)
                self._vfs.write_bytes(target, data)

            self.mark_done(item_id)
            return True, f"Скачано: {target}"
        except Exception as e:
            self.mark_error(item_id, str(e))
            return False, f"Ошибка: {e}"


# ============================================================
#  Синглтон
# ============================================================

_downloads_instance = None


def downloads() -> DownloadsManager:
    global _downloads_instance
    if _downloads_instance is None:
        _downloads_instance = DownloadsManager()
    return _downloads_instance