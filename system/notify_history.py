"""
MountOS — История уведомлений.

Хранит все показанные уведомления в JSON-файле.
Используется центром уведомлений (ui/notif_center.py).

Формат записи:
    {
        "title":    "Приложение установлено",
        "text":     "Тест v1.0",
        "app_id":   "settings",     # опционально
        "icon":     "plus",         # опционально
        "time":     1735000000.0,   # unix timestamp
        "read":     False
    }
"""
import json
import time
from pathlib import Path

from system import paths


MAX_HISTORY = 100   # не храним больше 100 записей


class NotifyHistory:
    def __init__(self, path: Path = None):
        self.path = Path(path or paths.NOTIF_HISTORY)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._items = []
        self.load()

    # ---------- Загрузка / сохранение ----------

    def load(self):
        if not self.path.exists():
            self._items = []
            return
        try:
            raw = self.path.read_text(encoding="utf-8")
            data = json.loads(raw) if raw.strip() else []
            if isinstance(data, list):
                self._items = data
            else:
                self._items = []
        except Exception as e:
            print(f"[NotifyHistory] не удалось прочитать {self.path}: {e}")
            self._items = []

    def save(self):
        try:
            self.path.write_text(
                json.dumps(self._items, indent=2, ensure_ascii=False),
                encoding="utf-8")
        except Exception as e:
            print(f"[NotifyHistory] не удалось записать {self.path}: {e}")

    # ---------- Добавление ----------

    def add(self, title: str, text: str = "",
            app_id: str = "", icon: str = "") -> dict:
        entry = {
            "title":  title,
            "text":   text,
            "app_id": app_id,
            "icon":   icon,
            "time":   time.time(),
            "read":   False,
        }
        self._items.append(entry)
        # обрезаем до MAX_HISTORY (оставляем самые новые)
        if len(self._items) > MAX_HISTORY:
            self._items = self._items[-MAX_HISTORY:]
        self.save()
        return entry

    # ---------- Чтение ----------

    def all(self):
        return list(self._items)

    def latest(self, n: int = 20):
        return list(self._items[-n:])

    def unread_count(self) -> int:
        return sum(1 for it in self._items if not it.get("read"))

    def unread(self):
        return [it for it in self._items if not it.get("read")]

    # ---------- Отметки ----------

    def mark_read(self, index: int):
        if 0 <= index < len(self._items):
            self._items[index]["read"] = True
            self.save()

    def mark_all_read(self):
        changed = False
        for it in self._items:
            if not it.get("read"):
                it["read"] = True
                changed = True
        if changed:
            self.save()

    def remove(self, index: int):
        if 0 <= index < len(self._items):
            del self._items[index]
            self.save()

    def clear(self):
        self._items = []
        self.save()

    # ---------- Утилиты ----------

    def __len__(self):
        return len(self._items)

    def __repr__(self):
        return f"<NotifyHistory items={len(self._items)} unread={self.unread_count()}>"


# ============================================================
#  Глобальный синглтон
# ============================================================

_instance = None


def history() -> NotifyHistory:
    """Возвращает глобальную историю уведомлений (создаётся один раз)."""
    global _instance
    if _instance is None:
        _instance = NotifyHistory()
    return _instance


def pretty_time(ts: float) -> str:
    """Превращает unix timestamp в человекочитаемую строку."""
    if not ts:
        return ""
    now = time.time()
    diff = now - ts
    if diff < 60:
        return "только что"
    if diff < 3600:
        m = int(diff // 60)
        return f"{m} мин назад"
    if diff < 86400:
        h = int(diff // 3600)
        return f"{h} ч назад"
    # иначе — дата
    import datetime
    dt = datetime.datetime.fromtimestamp(ts)
    today = datetime.date.today()
    if dt.date() == today:
        return dt.strftime("%H:%M")
    if dt.year == today.year:
        return dt.strftime("%d.%m %H:%M")
    return dt.strftime("%d.%m.%Y %H:%M")