"""
MountOS — Виртуальная файловая система.
Песочница в system/storage/user_data/home/.
"""
import os
import shutil
from pathlib import Path

from system import paths


class VFS:
    def __init__(self, base_dir=None):
        # Игнорируем base_dir — используем наш путь
        self.root = paths.HOME_DIR
        self.root.mkdir(parents=True, exist_ok=True)

    # ---- Пути ----
    def _resolve(self, path: str) -> Path:
        if not path or path == "/":
            return self.root
        clean = path.lstrip("/").replace("\\", "/")
        target = (self.root / clean).resolve()
        try:
            target.relative_to(self.root.resolve())
        except ValueError:
            raise PermissionError(f"Путь вне песочницы MountOS: {path}")
        return target

    def home(self) -> str:
        return "/"

    # ---- Чтение ----
    def listdir(self, path: str = "/"):
        p = self._resolve(path)
        if not p.exists():
            return []
        items = []
        for entry in sorted(p.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower())):
            try:
                stat = entry.stat()
                items.append({
                    "name": entry.name,
                    "path": self._to_vpath(entry),
                    "is_dir": entry.is_dir(),
                    "size": 0 if entry.is_dir() else stat.st_size,
                    "mtime": stat.st_mtime,
                })
            except (OSError, PermissionError):
                continue
        return items

    def exists(self, path: str) -> bool:
        try:
            return self._resolve(path).exists()
        except PermissionError:
            return False

    def is_dir(self, path: str) -> bool:
        try:
            return self._resolve(path).is_dir()
        except PermissionError:
            return False

    def read_text(self, path: str, default="") -> str:
        p = self._resolve(path)
        if not p.exists():
            return default
        try:
            return p.read_text(encoding="utf-8")
        except Exception:
            return default

    def read_bytes(self, path: str) -> bytes:
        return self._resolve(path).read_bytes()

    # ---- Запись ----
    def write_text(self, path: str, text: str):
        p = self._resolve(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    def write_bytes(self, path: str, data: bytes):
        p = self._resolve(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)

    def mkdir(self, path: str):
        self._resolve(path).mkdir(parents=True, exist_ok=True)

    def delete(self, path: str):
        p = self._resolve(path)
        if not p.exists():
            return
        if p.is_dir():
            shutil.rmtree(p)
        else:
            p.unlink()

    def rename(self, old: str, new: str):
        self._resolve(old).rename(self._resolve(new))

    def copy(self, src: str, dst: str):
        s = self._resolve(src)
        d = self._resolve(dst)
        if s.is_dir():
            shutil.copytree(s, d)
        else:
            d.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(s, d)

    # ---- Утилиты ----
    def _to_vpath(self, p: Path) -> str:
        rel = p.relative_to(self.root)
        return "/" + rel.as_posix()

    def join(self, *parts) -> str:
        joined = "/".join(str(p).strip("/") for p in parts if p)
        return "/" + joined

    def basename(self, path: str) -> str:
        return os.path.basename(path.rstrip("/")) or "/"

    def parent(self, path: str) -> str:
        path = path.rstrip("/")
        if not path or path == "/":
            return "/"
        p = os.path.dirname(path)
        return p or "/"

    # ---- Инициализация ----
    def ensure_default_structure(self):
        for folder in ["Documents", "Pictures", "Notes", "Downloads", "Music"]:
            self.mkdir(f"/{folder}")

        readme = "/Documents/readme.txt"
        if not self.exists(readme):
            self.write_text(readme,
                "Добро пожаловать в MountOS!\n\n"
                "Это виртуальная файловая система.\n"
                "Всё, что ты создаёшь здесь — лежит в\n"
                "system/storage/user_data/home/ и не трогает реальный диск.\n"
            )