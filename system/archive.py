"""
MountOS — Работа с архивами в VFS.

Позволяет:
  • Упаковать файлы и папки в ZIP прямо в VFS
  • Распаковать ZIP в указанную папку
  • Просмотреть содержимое архива без распаковки
  • Поддержка форматов: ZIP, TAR, TAR.GZ, TAR.BZ2, GZ, BZ2

Всё работает в виртуальной файловой системе MountOS —
без обращения к реальному диску.

API:
    from system.archive import ArchiveManager
    arc = ArchiveManager(vfs)
    arc.pack(["/Documents/a.txt", "/Documents/b.txt"],
             "/Documents/archive.zip")
    arc.unpack("/Documents/archive.zip", "/Documents/extracted/")
    arc.list_contents("/Documents/archive.zip")  # список файлов
"""

import os
import io
import zipfile
import tarfile
import gzip
import bz2

from PySide6.QtCore import QObject, Signal


# ============================================================
#  Поддерживаемые форматы
# ============================================================

# Форматы, которые можно создать:
PACK_FORMATS = {
    ".zip":   "ZIP архив",
    ".tar":   "TAR архив",
    ".tar.gz": "TAR.GZ (сжатый)",
    ".tgz":   "TGZ (то же, что TAR.GZ)",
    ".tar.bz2": "TAR.BZ2 (сильно сжатый)",
    ".gz":    "GZIP (один файл)",
    ".bz2":   "BZIP2 (один файл)",
}

# Форматы, которые можно распаковать:
UNPACK_FORMATS = {".zip", ".tar", ".tar.gz", ".tgz", ".tar.bz2",
                  ".gz", ".bz2"}


# ============================================================
#  Менеджер архивов
# ============================================================

class ArchiveManager(QObject):
    """
    Работа с архивами в VFS.

    Все операции — через объект VFS MountOS.
    """

    progress = Signal(str)   # сообщение о прогрессе

    def __init__(self, vfs):
        super().__init__()
        self.vfs = vfs

    # ------------------------------------------------------------
    #  Определение формата
    # ------------------------------------------------------------

    @staticmethod
    def is_archive(path: str) -> bool:
        """Является ли файл архивом по расширению."""
        low = path.lower()
        for ext in UNPACK_FORMATS:
            if low.endswith(ext):
                return True
        return False

    @staticmethod
    def format_of(path: str) -> str:
        """Возвращает расширение (одно из UNPACK_FORMATS) или ''."""
        low = path.lower()
        # Сначала проверяем длинные (tar.gz, tar.bz2)
        for ext in (".tar.gz", ".tar.bz2", ".tgz"):
            if low.endswith(ext):
                return ext
        # Потом короткие
        for ext in (".zip", ".tar", ".gz", ".bz2"):
            if low.endswith(ext):
                return ext
        return ""

    # ------------------------------------------------------------
    #  Упаковка (создание архива)
    # ------------------------------------------------------------

    def pack(self, sources: list, dest_path: str) -> tuple:
        """
        Упаковывает список файлов/папок из VFS в архив.

        sources   — список путей в VFS (/Documents/a.txt, /Documents/folder)
        dest_path — путь к создаваемому архиву

        Возвращает (success: bool, message: str)
        """
        if not sources:
            return False, "Нечего упаковывать"

        fmt = self.format_of(dest_path)
        if not fmt:
            return False, f"Неизвестный формат: {dest_path}"

        try:
            if fmt == ".zip":
                return self._pack_zip(sources, dest_path)
            elif fmt in (".tar", ".tar.gz", ".tgz", ".tar.bz2"):
                return self._pack_tar(sources, dest_path, fmt)
            elif fmt in (".gz", ".bz2"):
                return self._pack_single(sources, dest_path, fmt)
            else:
                return False, f"Формат {fmt} не поддерживается для упаковки"
        except Exception as e:
            return False, f"Ошибка упаковки: {e}"

    def _collect_files(self, vfs_path: str) -> list:
        """
        Рекурсивно собирает список файлов внутри VFS-пути.
        Возвращает [(vfs_path, arcname), ...] где arcname — путь внутри архива.
        """
        result = []
        if not self.vfs.exists(vfs_path):
            return result

        base_name = self.vfs.basename(vfs_path)

        if self.vfs.is_dir(vfs_path):
            # Папка — обходим рекурсивно
            def walk(path, prefix):
                for it in self.vfs.listdir(path):
                    arc = f"{prefix}/{it['name']}"
                    if it["is_dir"]:
                        walk(it["path"], arc)
                    else:
                        result.append((it["path"], arc))
            walk(vfs_path, base_name)
        else:
            # Один файл
            result.append((vfs_path, base_name))

        return result

    def _pack_zip(self, sources: list, dest_path: str) -> tuple:
        buf = io.BytesIO()
        total = 0

        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for src in sources:
                files = self._collect_files(src)
                for vfs_path, arcname in files:
                    try:
                        data = self.vfs.read_bytes(vfs_path)
                        zf.writestr(arcname, data)
                        total += 1
                        self.progress.emit(f"Упаковано: {arcname}")
                    except Exception as e:
                        self.progress.emit(f"Ошибка с {vfs_path}: {e}")

        # Записываем архив в VFS
        self.vfs.write_bytes(dest_path, buf.getvalue())
        size_kb = len(buf.getvalue()) / 1024
        return True, f"Создан ZIP: {dest_path}\n{total} файлов, {size_kb:.1f} КБ"

    def _pack_tar(self, sources: list, dest_path: str, fmt: str) -> tuple:
        # Определяем режим сжатия
        if fmt in (".tar.gz", ".tgz"):
            mode = "w:gz"
        elif fmt == ".tar.bz2":
            mode = "w:bz2"
        else:
            mode = "w"

        buf = io.BytesIO()
        total = 0

        with tarfile.open(fileobj=buf, mode=mode) as tf:
            for src in sources:
                files = self._collect_files(src)
                for vfs_path, arcname in files:
                    try:
                        data = self.vfs.read_bytes(vfs_path)
                        info = tarfile.TarInfo(name=arcname)
                        info.size = len(data)
                        info.mtime = 0
                        tf.addfile(info, io.BytesIO(data))
                        total += 1
                        self.progress.emit(f"Упаковано: {arcname}")
                    except Exception as e:
                        self.progress.emit(f"Ошибка с {vfs_path}: {e}")

        self.vfs.write_bytes(dest_path, buf.getvalue())
        size_kb = len(buf.getvalue()) / 1024
        return True, f"Создан {fmt}: {dest_path}\n{total} файлов, {size_kb:.1f} КБ"

    def _pack_single(self, sources: list, dest_path: str, fmt: str) -> tuple:
        if len(sources) != 1:
            return False, "GZ/BZ2 сжимают только один файл. Используй .zip или .tar.gz"
        src = sources[0]
        if self.vfs.is_dir(src):
            return False, "GZ/BZ2 не могут сжимать папки"

        data = self.vfs.read_bytes(src)
        if fmt == ".gz":
            compressed = gzip.compress(data)
        elif fmt == ".bz2":
            compressed = bz2.compress(data)
        else:
            return False, f"Неизвестный одиночный формат: {fmt}"

        self.vfs.write_bytes(dest_path, compressed)
        ratio = (1 - len(compressed) / max(1, len(data))) * 100
        return True, (f"Сжато: {src} → {dest_path}\n"
                       f"{len(data)} → {len(compressed)} байт "
                       f"({ratio:.0f}% экономии)")

    # ------------------------------------------------------------
    #  Распаковка
    # ------------------------------------------------------------

    def unpack(self, archive_path: str, dest_dir: str = None) -> tuple:
        """
        Распаковывает архив в папку.

        archive_path — путь к архиву в VFS
        dest_dir     — куда распаковать (по умолчанию — рядом с архивом)

        Возвращает (success, message)
        """
        if not self.vfs.exists(archive_path):
            return False, "Архив не найден"

        fmt = self.format_of(archive_path)
        if not fmt:
            return False, "Неизвестный формат архива"

        # Папка назначения по умолчанию
        if dest_dir is None:
            base = archive_path
            for ext in (".tar.gz", ".tar.bz2", ".tgz", ".zip", ".tar", ".gz", ".bz2"):
                if base.lower().endswith(ext):
                    base = base[:-len(ext)]
                    break
            dest_dir = base + "/"

        try:
            self.vfs.mkdir(dest_dir)

            if fmt == ".zip":
                return self._unpack_zip(archive_path, dest_dir)
            elif fmt in (".tar", ".tar.gz", ".tgz", ".tar.bz2"):
                return self._unpack_tar(archive_path, dest_dir, fmt)
            elif fmt in (".gz", ".bz2"):
                return self._unpack_single(archive_path, dest_dir, fmt)
            else:
                return False, f"Формат {fmt} не поддерживается"
        except Exception as e:
            return False, f"Ошибка распаковки: {e}"

    def _unpack_zip(self, archive_path: str, dest_dir: str) -> tuple:
        data = self.vfs.read_bytes(archive_path)
        total = 0

        with zipfile.ZipFile(io.BytesIO(data), "r") as zf:
            for info in zf.infolist():
                name = info.filename
                if name.endswith("/"):
                    # Это папка
                    self.vfs.mkdir(self.vfs.join(dest_dir, name.rstrip("/")))
                    continue

                # Защита от path traversal (../)
                safe_name = name.replace("..", "_")
                target = self.vfs.join(dest_dir, safe_name)
                # Убеждаемся, что папка существует
                parent = self.vfs.parent(target)
                if parent and parent != "/":
                    self.vfs.mkdir(parent)

                content = zf.read(info)
                self.vfs.write_bytes(target, content)
                total += 1
                self.progress.emit(f"Распаковано: {safe_name}")

        return True, f"Распакован ZIP: {total} файлов → {dest_dir}"

    def _unpack_tar(self, archive_path: str, dest_dir: str, fmt: str) -> tuple:
        data = self.vfs.read_bytes(archive_path)
        if fmt in (".tar.gz", ".tgz"):
            mode = "r:gz"
        elif fmt == ".tar.bz2":
            mode = "r:bz2"
        else:
            mode = "r"

        total = 0
        with tarfile.open(fileobj=io.BytesIO(data), mode=mode) as tf:
            for member in tf.getmembers():
                name = member.name
                if member.isdir():
                    self.vfs.mkdir(self.vfs.join(dest_dir, name))
                    continue
                if not member.isfile():
                    continue

                safe_name = name.replace("..", "_")
                target = self.vfs.join(dest_dir, safe_name)
                parent = self.vfs.parent(target)
                if parent and parent != "/":
                    self.vfs.mkdir(parent)

                f = tf.extractfile(member)
                if f is None:
                    continue
                content = f.read()
                self.vfs.write_bytes(target, content)
                total += 1
                self.progress.emit(f"Распаковано: {safe_name}")

        return True, f"Распакован {fmt}: {total} файлов → {dest_dir}"

    def _unpack_single(self, archive_path: str, dest_dir: str, fmt: str) -> tuple:
        data = self.vfs.read_bytes(archive_path)

        if fmt == ".gz":
            decompressed = gzip.decompress(data)
        elif fmt == ".bz2":
            decompressed = bz2.decompress(data)
        else:
            return False, f"Неизвестный формат: {fmt}"

        # Имя файла — базовое имя архива без .gz/.bz2
        base_name = self.vfs.basename(archive_path)
        if base_name.lower().endswith(fmt):
            base_name = base_name[:-len(fmt)]

        target = self.vfs.join(dest_dir, base_name)
        self.vfs.write_bytes(target, decompressed)

        return True, f"Распаковано: {target} ({len(decompressed)} байт)"

    # ------------------------------------------------------------
    #  Просмотр содержимого
    # ------------------------------------------------------------

    def list_contents(self, archive_path: str) -> list:
        """
        Возвращает список файлов внутри архива.
        Каждый — dict: {"name", "size", "is_dir"}
        """
        if not self.vfs.exists(archive_path):
            return []

        fmt = self.format_of(archive_path)
        if not fmt:
            return []

        result = []
        try:
            data = self.vfs.read_bytes(archive_path)

            if fmt == ".zip":
                with zipfile.ZipFile(io.BytesIO(data), "r") as zf:
                    for info in zf.infolist():
                        result.append({
                            "name": info.filename,
                            "size": info.file_size,
                            "compressed": info.compress_size,
                            "is_dir": info.filename.endswith("/"),
                        })
            elif fmt in (".tar", ".tar.gz", ".tgz", ".tar.bz2"):
                if fmt in (".tar.gz", ".tgz"):
                    mode = "r:gz"
                elif fmt == ".tar.bz2":
                    mode = "r:bz2"
                else:
                    mode = "r"
                with tarfile.open(fileobj=io.BytesIO(data), mode=mode) as tf:
                    for member in tf.getmembers():
                        result.append({
                            "name": member.name,
                            "size": member.size,
                            "compressed": member.size,
                            "is_dir": member.isdir(),
                        })
            elif fmt in (".gz", ".bz2"):
                # Один файл
                base_name = self.vfs.basename(archive_path)
                for ext in (".gz", ".bz2"):
                    if base_name.lower().endswith(ext):
                        base_name = base_name[:-len(ext)]
                        break
                result.append({
                    "name": base_name,
                    "size": -1,
                    "compressed": len(data),
                    "is_dir": False,
                })
        except Exception as e:
            print(f"[Archive] list error: {e}")

        return result


# ============================================================
#  Утилиты
# ============================================================

def human_size(n: int) -> str:
    """Форматирует размер в читаемый вид."""
    if n < 0:
        return "—"
    units = ["Б", "КБ", "МБ", "ГБ"]
    f = float(n)
    for u in units:
        if f < 1024:
            return f"{f:.1f} {u}"
        f /= 1024
    return f"{f:.1f} ТБ"