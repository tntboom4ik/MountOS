"""
MountOS — Превью файлов.

Генерирует превью для файлов в проводнике:
  • Изображения (PNG, JPG, BMP, GIF, WEBP) — уменьшенная копия
  • Текст / код — первые строки
  • Аудио — иконка + метаданные
  • Видео — иконка + метаданные
  • Архивы — иконка + список содержимого
  • JSON — красиво отформатировано
  • По расширению — подходящая иконка

Кэш превью — чтобы не пересчитывать повторно.

API:
    from ui.file_preview import FilePreview
    prev = FilePreview(vfs)
    pixmap = prev.get_pixmap("/Documents/photo.png", size=64)
    text = prev.get_text_preview("/Documents/note.txt", lines=10)
"""

import os
import json

from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QSize, QRectF
from PySide6.QtGui import (QPixmap, QImage, QPainter, QColor, QPen, QBrush,
                            QFont, QIcon, QPainterPath, QLinearGradient)

from ui.icons import get_icon


# ============================================================
#  Группы расширений
# ============================================================

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp",
             ".tiff", ".tif", ".ico", ".svg"}

TEXT_EXT = {".txt", ".md", ".log", ".json", ".py", ".html", ".css",
            ".js", ".csv", ".ini", ".cfg", ".xml", ".yml", ".yaml",
            ".toml", ".sh", ".bat", ".c", ".cpp", ".h", ".java"}

AUDIO_EXT = {".mp3", ".wav", ".ogg", ".flac", ".m4a", ".aac", ".opus"}

VIDEO_EXT = {".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".webm"}

ARCHIVE_EXT = {".zip", ".tar", ".gz", ".bz2", ".7z", ".rar",
               ".tar.gz", ".tgz", ".tar.bz2"}

CODE_EXT = {".py", ".js", ".html", ".css", ".json", ".xml", ".c", ".cpp"}


# ============================================================
#  Определение типа файла
# ============================================================

def file_kind(name: str) -> str:
    """
    Возвращает тип файла по расширению:
    image | text | audio | video | archive | code | folder | other
    """
    low = name.lower()
    # tar.gz / tar.bz2 — проверяем раньше
    for ext in (".tar.gz", ".tar.bz2"):
        if low.endswith(ext):
            return "archive"

    ext = os.path.splitext(low)[1]
    if ext in IMAGE_EXT:
        return "image"
    if ext in AUDIO_EXT:
        return "audio"
    if ext in VIDEO_EXT:
        return "video"
    if ext in ARCHIVE_EXT:
        return "archive"
    if ext in CODE_EXT:
        return "code"
    if ext in TEXT_EXT:
        return "text"
    return "other"


def icon_for_kind(kind: str) -> str:
    """Какая иконка MountOS подходит для типа."""
    return {
        "image":   "gallery",
        "text":    "notes",
        "audio":   "music",
        "video":   "browser",
        "archive": "files",
        "code":    "terminal",
        "folder":  "files",
        "other":   "files",
    }.get(kind, "files")


# ============================================================
#  Менеджер превью
# ============================================================

class FilePreview:
    """
    Генерирует превью файлов из VFS.
    Кэширует результаты для скорости.
    """

    def __init__(self, vfs):
        self.vfs = vfs
        self._cache = {}          # path -> QPixmap
        self._text_cache = {}     # path -> str
        self._max_cache = 100     # максимум элементов в кэше

    # ------------------------------------------------------------
    #  Публичный API
    # ------------------------------------------------------------

    def get_pixmap(self, vfs_path: str, size: int = 64,
                    is_dir: bool = False) -> QPixmap:
        """
        Возвращает превью-картинку для файла.
        Для картинок — уменьшенная версия.
        Для остальных — иконка по типу.
        """
        if is_dir:
            return get_icon("files", size, "#FFFFFF")

        # Кэш
        key = (vfs_path, size)
        if key in self._cache:
            return self._cache[key]

        pm = None
        kind = file_kind(vfs_path)

        if kind == "image":
            pm = self._make_image_preview(vfs_path, size)

        if pm is None:
            # Fallback — иконка по типу
            icon_name = icon_for_kind(kind)
            pm = get_icon(icon_name, size, "#FFFFFF")

        # Ограничиваем кэш
        if len(self._cache) > self._max_cache:
            # Удаляем ~20% старых
            for k in list(self._cache.keys())[:20]:
                del self._cache[k]
        self._cache[key] = pm
        return pm

    def get_text_preview(self, vfs_path: str, max_lines: int = 15,
                          max_chars: int = 500) -> str:
        """
        Первые строки файла (для текстовых).
        """
        if vfs_path in self._text_cache:
            return self._text_cache[vfs_path]

        if self.vfs is None:
            return ""

        try:
            data = self.vfs.read_bytes(vfs_path)
            # Пробуем декодировать
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                try:
                    text = data.decode("cp1251")
                except UnicodeDecodeError:
                    text = data.decode("latin-1", errors="replace")

            # Обрезаем
            lines = text.split("\n")[:max_lines]
            result = "\n".join(lines)
            if len(result) > max_chars:
                result = result[:max_chars] + "…"

            # Кэшируем
            if len(self._text_cache) > self._max_cache:
                for k in list(self._text_cache.keys())[:20]:
                    del self._text_cache[k]
            self._text_cache[vfs_path] = result
            return result
        except Exception as e:
            print(f"[Preview] text: {e}")
            return ""

    def get_json_preview(self, vfs_path: str, max_chars: int = 500) -> str:
        """Красивое превью JSON."""
        if self.vfs is None:
            return ""
        try:
            raw = self.vfs.read_text(vfs_path, "")
            data = json.loads(raw)
            pretty = json.dumps(data, ensure_ascii=False, indent=2)
            if len(pretty) > max_chars:
                pretty = pretty[:max_chars] + "\n…"
            return pretty
        except Exception:
            return ""

    def get_image_info(self, vfs_path: str) -> dict:
        """
        Возвращает метаданные картинки:
        {"width", "height", "format", "size"}
        """
        if self.vfs is None:
            return {}
        try:
            data = self.vfs.read_bytes(vfs_path)
            img = QImage()
            if not img.loadFromData(data):
                return {}
            return {
                "width": img.width(),
                "height": img.height(),
                "format": img.format(),
                "size": len(data),
            }
        except Exception:
            return {}

    def get_archive_preview(self, vfs_path: str, max_items: int = 10) -> str:
        """Превью содержимого архива."""
        try:
            from system.archive import ArchiveManager
            arc = ArchiveManager(self.vfs)
            items = arc.list_contents(vfs_path)
            if not items:
                return "(архив пуст или повреждён)"
            lines = []
            for it in items[:max_items]:
                icon = "📁" if it.get("is_dir") else "📄"
                lines.append(f"{icon} {it['name']}")
            if len(items) > max_items:
                lines.append(f"…и ещё {len(items) - max_items} файлов")
            return "\n".join(lines)
        except Exception as e:
            return f"(ошибка чтения архива: {e})"

    # ------------------------------------------------------------
    #  Внутренние генераторы
    # ------------------------------------------------------------

    def _make_image_preview(self, vfs_path: str, size: int) -> QPixmap:
        """Создаёт уменьшенную копию картинки с закруглением."""
        if self.vfs is None:
            return None
        try:
            data = self.vfs.read_bytes(vfs_path)
            if not data:
                return None

            # Загружаем QImage
            img = QImage()
            if not img.loadFromData(data):
                return None

            # Скейлим с сохранением пропорций
            scaled = img.scaled(size, size,
                                Qt.KeepAspectRatio,
                                Qt.SmoothTransformation)

            # Отрисовываем с закруглением на прозрачном фоне
            result = QPixmap(size, size)
            result.fill(Qt.transparent)

            p = QPainter(result)
            p.setRenderHint(QPainter.Antialiasing)
            p.setRenderHint(QPainter.SmoothPixmapTransform)

            # Центрируем
            x = (size - scaled.width()) // 2
            y = (size - scaled.height()) // 2

            # Маска закругления
            path = QPainterPath()
            path.addRoundedRect(QRectF(x, y, scaled.width(), scaled.height()),
                                6, 6)
            p.setClipPath(path)
            p.drawImage(x, y, scaled)

            p.end()
            return result
        except Exception as e:
            print(f"[Preview] image: {e}")
            return None

    def make_thumbnail_icon(self, vfs_path: str, base_icon: str = "files",
                             size: int = 40, overlay_kind: str = None) -> QPixmap:
        """
        Создаёт иконку с наложением — например, для папок с картинкой внутри.
        """
        pm = QPixmap(size, size)
        pm.fill(Qt.transparent)

        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)

        # Базовая иконка
        base = get_icon(base_icon, size, "#FFFFFF")
        p.drawPixmap(0, 0, base)

        # Оверлей-точка в правом нижнем углу
        if overlay_kind:
            dot_size = int(size * 0.35)
            x = size - dot_size
            y = size - dot_size

            color = {
                "image":   QColor("#6EE7B7"),
                "audio":   QColor("#B388FF"),
                "video":   QColor("#FF6B8A"),
                "text":    QColor("#6EC6FF"),
                "archive": QColor("#FFB86C"),
            }.get(overlay_kind, QColor("#6EC6FF"))

            p.setBrush(QBrush(color))
            p.setPen(QPen(QColor("white"), 1.5))
            p.drawEllipse(x, y, dot_size, dot_size)

        p.end()
        return pm

    # ------------------------------------------------------------
    #  Очистка
    # ------------------------------------------------------------

    def clear_cache(self):
        self._cache.clear()
        self._text_cache.clear()

    def invalidate(self, vfs_path: str):
        """Удаляет из кэша один файл (если изменился)."""
        keys_to_remove = [k for k in self._cache.keys()
                          if k[0] == vfs_path]
        for k in keys_to_remove:
            del self._cache[k]
        if vfs_path in self._text_cache:
            del self._text_cache[vfs_path]