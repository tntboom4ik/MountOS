"""
MountOS — Хранилище настроек.
Сохраняет SettingsState в JSON внутри MountOS/system/storage/.
"""
import json
from pathlib import Path


class SettingsStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._data = {}
        self.load()

    def load(self):
        if not self.path.exists():
            self._data = {}
            return
        try:
            raw = self.path.read_text(encoding="utf-8")
            self._data = json.loads(raw) if raw.strip() else {}
        except Exception as e:
            print(f"[SettingsStore] load: {e}")
            self._data = {}

    def save(self):
        try:
            self.path.write_text(
                json.dumps(self._data, indent=2, ensure_ascii=False),
                encoding="utf-8")
        except Exception as e:
            print(f"[SettingsStore] save: {e}")

    def get(self, key, default=None):
        return self._data.get(key, default)

    def set(self, key, value):
        self._data[key] = value
        self.save()

    def delete(self, key):
        if key in self._data:
            del self._data[key]
            self.save()

    def clear(self):
        self._data = {}
        self.save()

    def all(self):
        return dict(self._data)