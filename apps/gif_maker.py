"""
MountOS — Создатель GIF-анимаций.

Собирает несколько PNG/JPG из VFS в один GIF:
  • Список кадров — можно добавлять/удалять/менять порядок
  • Настройка задержки между кадрами (10..2000 мс)
  • Настройка количества повторов (0 = бесконечно)
  • Предпросмотр каждого кадра
  • Предпросмотр всей анимации
  • Сохранение в VFS

GIF генерируется на чистом Python — без Pillow.
Реализация формата GIF89a (LZW-сжатие).

Установка: apps/gif_maker.py + перезапуск MountOS.
"""

import io
import os
import time
import struct
from collections import deque

from PySide6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QLabel,
                                QPushButton, QListWidget, QListWidgetItem,
                                QInputDialog, QMessageBox, QSpinBox,
                                QComboBox, QScrollArea, QFrame, QSizePolicy,
                                QAbstractItemView)
from PySide6.QtCore import Qt, QTimer, QSize, QBuffer, QByteArray
from PySide6.QtGui import QPixmap, QImage, QPainter, QColor, QIcon, QFont

from ui.icons import get_icon
from ui.settings_state import state
from ui.context_menu import make_menu

APP_NAME = "GIF-мастер"
APP_ICON = "gallery"
APP_VERSION = "1.0"
APP_AUTHOR = "MountOS"


GIF_OUT_DIR = "/Pictures/GIF"


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


# ============================================================
#  GIF-энкодер (чистый Python, GIF89a)
# ============================================================

class GIFWriter:
    """
    Простой GIF89a энкодер.
    Принимает список QImage, сохраняет много-кадровый GIF.
    """

    def __init__(self, width: int, height: int,
                 delay_ms: int = 500, loop: int = 0):
        self.width = width
        self.height = height
        self.delay_cs = max(1, min(65535, delay_ms // 10))  # в сотых сек
        self.loop = loop   # 0 = бесконечно
        self.frames = []   # список (palette, indices) на кадр
        self.global_palette = None

    def add_frame(self, image: QImage):
        """Добавляет кадр. Квантует цвета, готовит индексы."""
        # Масштабируем под целевой размер
        img = image.convertToFormat(QImage.Format_RGB888)
        if img.width() != self.width or img.height() != self.height:
            img = img.scaled(self.width, self.height,
                             Qt.IgnoreAspectRatio, Qt.SmoothTransformation)

        # Собираем пиксели
        pixels = []
        for y in range(self.height):
            for x in range(self.width):
                c = img.pixelColor(x, y)
                pixels.append((c.red(), c.green(), c.blue()))

        # Квантование: собираем цвета, до 256
        palette = self._build_palette(pixels, max_colors=255)

        # Индексы
        indices = bytearray()
        color_map = {c: i for i, c in enumerate(palette)}
        for px in pixels:
            if px in color_map:
                indices.append(color_map[px])
            else:
                # Ближайший цвет (простое расстояние)
                best_i = 0
                best_d = 1 << 30
                for i, pc in enumerate(palette):
                    d = ((px[0] - pc[0]) ** 2 +
                         (px[1] - pc[1]) ** 2 +
                         (px[2] - pc[2]) ** 2)
                    if d < best_d:
                        best_d = d
                        best_i = i
                indices.append(best_i)

        # Общая палитра для GIF
        if self.global_palette is None:
            self.global_palette = palette
        else:
            # Мержим — просто заменяем на текущую
            # (упрощение: одна палитра на кадр, локальная)
            pass

        self.frames.append((palette, bytes(indices)))

    def _build_palette(self, pixels, max_colors: int = 255) -> list:
        """Строит палитру до max_colors цветов. Квантование медианным срезом."""
        if len(pixels) <= max_colors:
            return list(dict.fromkeys(pixels))

        # Простое квантование: по сетке 4 бита на канал → сжатие
        # Если всё равно много — уменьшаем шаг
        for step in [1, 2, 4, 8, 16, 32, 64, 128]:
            quantized = {}
            for px in pixels:
                q = (
                    (px[0] // step) * step,
                    (px[1] // step) * step,
                    (px[2] // step) * step,
                )
                quantized[q] = quantized.get(q, 0) + 1
                if len(quantized) > max_colors and step == 1:
                    break
            if len(quantized) <= max_colors:
                # Сортируем по частоте, берём топ
                sorted_colors = sorted(quantized.items(),
                                       key=lambda kv: -kv[1])
                return [c for c, _ in sorted_colors[:max_colors]]
        # Fallback — первые max_colors
        return list(dict.fromkeys(pixels))[:max_colors]

    def to_bytes(self) -> bytes:
        """Возвращает полный GIF как байты."""
        if not self.frames:
            return b""

        # Используем палитру первого кадра как глобальную
        global_palette = self.frames[0][0]

        out = io.BytesIO()

        # ---- Header ----
        out.write(b"GIF89a")

        # ---- Logical Screen Descriptor ----
        out.write(struct.pack("<HH", self.width, self.height))
        # packed: global color table flag, color resolution, sort, size
        # 256 цветов → size = 7 (2^7 = 128... но нужно 8 бит = 7 в 3 битах)
        gct_size = 7  # 2^(7+1) = 256
        packed = 0b10000000 | (7 << 4) | gct_size  # gct flag=1, color res=7
        out.write(bytes([packed, 0, 0]))

        # ---- Global Color Table ----
        # 256 записей × 3 байта
        table = bytearray()
        for i in range(256):
            if i < len(global_palette):
                r, g, b = global_palette[i]
                table += bytes([r, g, b])
            else:
                table += b"\x00\x00\x00"
        out.write(bytes(table))

        # ---- Netscape Extension (для повтора) ----
        if self.loop >= 0:
            out.write(b"\x21\xFF\x0BNETSCAPE2.0")
            out.write(b"\x03\x01")
            out.write(struct.pack("<H", self.loop))
            out.write(b"\x00")

        # ---- Кадры ----
        for palette, indices in self.frames:
            # Graphic Control Extension (задержка + палитра)
            out.write(b"\x21\xF9\x04")
            disposal = 1  # не удалять, оставить
            # packed: disposal << 2 | user_input << 1 | transparent
            gce_packed = (disposal << 2) | 0
            out.write(bytes([gce_packed]))
            out.write(struct.pack("<H", self.delay_cs))
            out.write(b"\x00")  # transparent color index
            out.write(b"\x00")  # terminator

            # Image Descriptor
            out.write(b"\x2C")
            out.write(struct.pack("<HHHH", 0, 0, self.width, self.height))
            # packed: local color table flag = 0
            out.write(b"\x00")

            # LZW data
            lzw_data = self._lzw_encode(indices, min_code_size=8)
            # Image data
            while lzw_data:
                chunk = lzw_data[:255]
                lzw_data = lzw_data[255:]
                out.write(bytes([len(chunk)]))
                out.write(chunk)
            out.write(b"\x00")  # block terminator

        # ---- Trailer ----
        out.write(b"\x3B")

        return out.getvalue()

    def _lzw_encode(self, data: bytes, min_code_size: int = 8) -> bytes:
        """LZW-сжатие по спецификации GIF."""
        clear_code = 1 << min_code_size
        end_code = clear_code + 1
        code_size = min_code_size + 1
        next_code = end_code + 1
        dict_size = 1 << code_size
        max_code = (1 << 12) - 1

        dictionary = {bytes([i]): i for i in range(clear_code)}

        out_bits = []
        def write_code(code, size):
            for i in range(size - 1, -1, -1):
                out_bits.append((code >> i) & 1)

        write_code(clear_code, code_size)

        if not data:
            write_code(end_code, code_size)
        else:
            buffer = bytes([data[0]])
            for i in range(1, len(data)):
                next_byte = bytes([data[i]])
                candidate = buffer + next_byte
                if candidate in dictionary:
                    buffer = candidate
                else:
                    write_code(dictionary[buffer], code_size)
                    if next_code <= max_code:
                        dictionary[candidate] = next_code
                        next_code += 1
                        if next_code > (1 << code_size) and code_size < 12:
                            code_size += 1
                    else:
                        write_code(clear_code, code_size)
                        dictionary = {bytes([i]): i for i in range(clear_code)}
                        code_size = min_code_size + 1
                        next_code = end_code + 1
                    buffer = next_byte
            write_code(dictionary[buffer], code_size)
            write_code(end_code, code_size)

        # Упаковываем биты в байты (LSB first)
        result = bytearray()
        byte = 0
        bit_count = 0
        for b in out_bits:
            byte |= (b << bit_count)
            bit_count += 1
            if bit_count == 8:
                result.append(byte)
                byte = 0
                bit_count = 0
        if bit_count > 0:
            result.append(byte)

        return bytes(result)


# ============================================================
#  Основное приложение
# ============================================================

def build():
    root = QWidget()
    h = QHBoxLayout(root)
    h.setContentsMargins(0, 0, 0, 0)
    h.setSpacing(0)

    vfs = _get_vfs(root)

    # ============================================================
    #  Левая панель — кадры
    # ============================================================
    left = QWidget()
    left.setFixedWidth(340)
    left.setStyleSheet("""
        background: rgba(255,255,255,0.04);
        border-right: 1px solid rgba(255,255,255,0.08);
    """)
    ll = QVBoxLayout(left)
    ll.setContentsMargins(14, 16, 14, 16)
    ll.setSpacing(10)

    title = QLabel("🎬  GIF-мастер")
    title.setStyleSheet("color: white; font-size: 16px; font-weight: 600; padding: 2px;")
    ll.addWidget(title)

    hint = QLabel("Добавь PNG/JPG из VFS как кадры")
    hint.setStyleSheet("color: rgba(255,255,255,0.55); font-size: 11px;")
    hint.setWordWrap(True)
    ll.addWidget(hint)

    # Кнопки добавления
    btn_row = QHBoxLayout()
    btn_row.setSpacing(6)

    add_btn = QPushButton("＋ Добавить")
    add_btn.setCursor(Qt.PointingHandCursor)
    add_btn.setFixedHeight(34)
    add_btn.setStyleSheet("""
        QPushButton {
            background: rgba(110,198,255,0.20);
            color: white;
            border: 1px solid rgba(110,198,255,0.55);
            border-radius: 9px;
            font-size: 12px;
        }
        QPushButton:hover { background: rgba(110,198,255,0.40); }
    """)
    btn_row.addWidget(add_btn, 1)

    clear_btn = QPushButton("🗑")
    clear_btn.setFixedSize(34, 34)
    clear_btn.setToolTip("Очистить все кадры")
    clear_btn.setStyleSheet("""
        QPushButton {
            background: rgba(255,107,138,0.15);
            color: #FFA0B4;
            border: 1px solid rgba(255,107,138,0.40);
            border-radius: 9px;
            font-size: 14px;
        }
        QPushButton:hover { background: rgba(255,107,138,0.35); color: white; }
    """)
    btn_row.addWidget(clear_btn)

    ll.addLayout(btn_row)

    # Список кадров
    frames_list = QListWidget()
    frames_list.setSelectionMode(QAbstractItemView.SingleSelection)
    frames_list.setIconSize(QSize(64, 48))
    frames_list.setStyleSheet("""
        QListWidget {
            background: rgba(0,0,0,0.20);
            color: white;
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 10px;
            padding: 4px;
            font-size: 12px;
            outline: none;
        }
        QListWidget::item {
            padding: 6px;
            border-radius: 6px;
        }
        QListWidget::item:hover { background: rgba(255,255,255,0.08); }
        QListWidget::item:selected { background: rgba(110,198,255,0.30); }
    """)
    ll.addWidget(frames_list, 1)

    # Кнопки управления порядком
    order_row = QHBoxLayout()
    order_row.setSpacing(6)

    up_btn = QPushButton("▲ Вверх")
    up_btn.setFixedHeight(30)
    up_btn.setStyleSheet("""
        QPushButton {
            background: rgba(255,255,255,0.06);
            color: white;
            border: 1px solid rgba(255,255,255,0.12);
            border-radius: 8px;
            font-size: 11px;
        }
        QPushButton:hover { background: rgba(255,255,255,0.18); }
    """)
    order_row.addWidget(up_btn)

    down_btn = QPushButton("▼ Вниз")
    down_btn.setFixedHeight(30)
    down_btn.setStyleSheet(up_btn.styleSheet())
    order_row.addWidget(down_btn)

    del_btn = QPushButton("✕ Убрать")
    del_btn.setFixedHeight(30)
    del_btn.setStyleSheet("""
        QPushButton {
            background: rgba(255,107,138,0.15);
            color: #FFA0B4;
            border: 1px solid rgba(255,107,138,0.40);
            border-radius: 8px;
            font-size: 11px;
        }
        QPushButton:hover { background: rgba(255,107,138,0.35); color: white; }
    """)
    order_row.addWidget(del_btn)

    ll.addLayout(order_row)

    # ---- Настройки GIF ----
    opts_lbl = QLabel("НАСТРОЙКИ")
    opts_lbl.setStyleSheet("""
        color: rgba(255,255,255,0.45);
        font-size: 10px;
        font-weight: 700;
        letter-spacing: 1.5px;
        padding-top: 8px;
    """)
    ll.addWidget(opts_lbl)

    delay_row = QHBoxLayout()
    delay_lbl = QLabel("Задержка:")
    delay_lbl.setStyleSheet("color: rgba(255,255,255,0.75); font-size: 12px;")
    delay_row.addWidget(delay_lbl)

    delay_spin = QSpinBox()
    delay_spin.setRange(20, 5000)
    delay_spin.setValue(200)
    delay_spin.setSuffix(" мс")
    delay_spin.setSingleStep(50)
    delay_spin.setStyleSheet("""
        QSpinBox {
            background: rgba(255,255,255,0.08);
            color: white;
            border: 1px solid rgba(255,255,255,0.15);
            border-radius: 8px;
            padding: 4px 8px;
            font-size: 12px;
        }
    """)
    delay_row.addWidget(delay_spin, 1)
    ll.addLayout(delay_row)

    size_row = QHBoxLayout()
    size_lbl = QLabel("Размер:")
    size_lbl.setStyleSheet(delay_lbl.styleSheet())
    size_row.addWidget(size_lbl)

    size_combo = QComboBox()
    size_combo.addItems([
        "128×128", "256×256", "320×240", "480×360",
        "512×512", "640×480", "Как в кадре 1",
    ])
    size_combo.setCurrentIndex(3)
    size_combo.setStyleSheet("""
        QComboBox {
            background: rgba(255,255,255,0.08);
            color: white;
            border: 1px solid rgba(255,255,255,0.15);
            border-radius: 8px;
            padding: 4px 8px;
            font-size: 12px;
        }
    """)
    size_row.addWidget(size_combo, 1)
    ll.addLayout(size_row)

    loop_row = QHBoxLayout()
    loop_lbl = QLabel("Повтор:")
    loop_lbl.setStyleSheet(delay_lbl.styleSheet())
    loop_row.addWidget(loop_lbl)

    loop_combo = QComboBox()
    loop_combo.addItems([
        "Бесконечно", "1 раз", "2 раза", "3 раза", "5 раз", "10 раз",
    ])
    loop_combo.setStyleSheet(size_combo.styleSheet())
    loop_row.addWidget(loop_combo, 1)
    ll.addLayout(loop_row)

    # ---- Главная кнопка ----
    make_btn = QPushButton("🎬  Создать GIF")
    make_btn.setCursor(Qt.PointingHandCursor)
    make_btn.setFixedHeight(44)
    make_btn.setStyleSheet("""
        QPushButton {
            background: rgba(110,198,255,0.28);
            color: white;
            border: 1px solid rgba(110,198,255,0.65);
            border-radius: 12px;
            font-size: 14px;
            font-weight: 600;
        }
        QPushButton:hover { background: rgba(110,198,255,0.48); }
    """)
    ll.addWidget(make_btn)

    h.addWidget(left)

    # ============================================================
    #  Правая панель — предпросмотр
    # ============================================================
    right = QWidget()
    rl = QVBoxLayout(right)
    rl.setContentsMargins(30, 30, 30, 30)
    rl.setSpacing(14)

    preview_title = QLabel("Предпросмотр")
    preview_title.setStyleSheet("color: white; font-size: 14px; font-weight: 600;")
    preview_title.setAlignment(Qt.AlignCenter)
    rl.addWidget(preview_title)

    # Окно предпросмотра
    preview_label = QLabel()
    preview_label.setAlignment(Qt.AlignCenter)
    preview_label.setMinimumSize(400, 300)
    preview_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
    preview_label.setStyleSheet("""
        QLabel {
            background: rgba(0,0,0,0.30);
            border: 1px solid rgba(255,255,255,0.10);
            border-radius: 16px;
            color: rgba(255,255,255,0.40);
            font-size: 14px;
        }
    """)
    preview_label.setText("Добавь кадры слева")
    rl.addWidget(preview_label, 1)

    # Статус
    status_lbl = QLabel("Готов")
    status_lbl.setAlignment(Qt.AlignCenter)
    status_lbl.setStyleSheet("color: rgba(255,255,255,0.50); font-size: 11px;")
    rl.addWidget(status_lbl)

    # Прогресс анимации
    anim_row = QHBoxLayout()
    anim_row.setSpacing(8)

    play_anim_btn = QPushButton("▶  Проиграть предпросмотр")
    play_anim_btn.setCursor(Qt.PointingHandCursor)
    play_anim_btn.setFixedHeight(36)
    play_anim_btn.setStyleSheet("""
        QPushButton {
            background: rgba(255,255,255,0.08);
            color: white;
            border: 1px solid rgba(255,255,255,0.14);
            border-radius: 10px;
            font-size: 12px;
        }
        QPushButton:hover { background: rgba(255,255,255,0.20); }
    """)
    anim_row.addWidget(play_anim_btn)

    save_btn = QPushButton("💾 Сохранить в VFS")
    save_btn.setCursor(Qt.PointingHandCursor)
    save_btn.setFixedHeight(36)
    save_btn.setStyleSheet("""
        QPushButton {
            background: rgba(110,231,183,0.20);
            color: white;
            border: 1px solid rgba(110,231,183,0.55);
            border-radius: 10px;
            font-size: 12px;
        }
        QPushButton:hover { background: rgba(110,231,183,0.40); }
    """)
    anim_row.addWidget(save_btn)

    rl.addLayout(anim_row)

    h.addWidget(right, 1)

    # ============================================================
    #  Логика
    # ============================================================

    st = {
        "frames": [],        # список (path, name, QImage)
        "preview_index": 0,
        "playing": False,
        "last_gif_bytes": None,
    }

    # ---- Анимация предпросмотра ----
    anim_timer = QTimer(root)

    def anim_tick():
        if not st["frames"]:
            return
        st["preview_index"] = (st["preview_index"] + 1) % len(st["frames"])
        show_frame(st["preview_index"])

    anim_timer.timeout.connect(anim_tick)

    # ---- Показ кадра ----
    def show_frame(idx: int):
        if not st["frames"] or idx >= len(st["frames"]):
            return
        path, name, img = st["frames"][idx]
        pm = QPixmap.fromImage(img)
        # Масштабируем под окно
        max_w = max(300, preview_label.width() - 20)
        max_h = max(200, preview_label.height() - 20)
        scaled = pm.scaled(max_w, max_h,
                           Qt.KeepAspectRatio, Qt.SmoothTransformation)
        preview_label.setPixmap(scaled)
        preview_label.setText("")
        status_lbl.setText(f"Кадр {idx + 1} / {len(st['frames'])} — {name}")

    # ---- Список кадров ----
    def refresh_list():
        frames_list.clear()
        for i, (path, name, img) in enumerate(st["frames"]):
            icon_pm = QPixmap.fromImage(img).scaled(
                64, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            item = QListWidgetItem(QIcon(icon_pm),
                                    f"{i + 1}. {name[:25]}")
            item.setData(Qt.UserRole, i)
            frames_list.addItem(item)
        if not st["frames"]:
            preview_label.setPixmap(QPixmap())
            preview_label.setText("Добавь кадры слева")
            status_lbl.setText("Готов")

    # ---- Добавление кадров ----
    def add_frames():
        if vfs is None:
            QMessageBox.warning(root, "Ошибка", "VFS недоступна")
            return

        # Собираем все картинки из VFS
        all_files = []

        def walk(path, depth=0):
            if depth > 6:
                return
            try:
                items = vfs.listdir(path)
            except Exception:
                return
            for it in items:
                if it["is_dir"]:
                    walk(it["path"], depth + 1)
                else:
                    name_low = it["name"].lower()
                    if name_low.endswith((".png", ".jpg", ".jpeg",
                                          ".bmp", ".webp")):
                        all_files.append(it)

        walk("/")

        if not all_files:
            QMessageBox.information(root, "GIF-мастер",
                "В VFS нет изображений.\n"
                "Сохрани что-нибудь в /Pictures/ через Галерею или MountPaint.")
            return

        # Показываем список для выбора
        names = [f["path"] for f in all_files]
        selected, ok = QInputDialog.getItem(
            root, "Добавить кадр", "Выбери файл:",
            names, 0, False)
        if not ok:
            return

        # Загружаем
        try:
            data = vfs.read_bytes(selected)
            img = QImage()
            if not img.loadFromData(data):
                QMessageBox.warning(root, "Ошибка", "Не удалось загрузить")
                return
            name = os.path.basename(selected)
            st["frames"].append((selected, name, img))
            refresh_list()
            show_frame(len(st["frames"]) - 1)
        except Exception as e:
            QMessageBox.warning(root, "Ошибка", str(e))

    def clear_frames():
        if not st["frames"]:
            return
        ans = QMessageBox.question(root, "Очистить",
            "Удалить все кадры?", QMessageBox.Yes | QMessageBox.No)
        if ans == QMessageBox.Yes:
            st["frames"] = []
            refresh_list()

    def remove_current():
        item = frames_list.currentItem()
        if item is None:
            return
        idx = int(item.data(Qt.UserRole))
        if 0 <= idx < len(st["frames"]):
            del st["frames"][idx]
            refresh_list()
            if st["frames"]:
                show_frame(min(idx, len(st["frames"]) - 1))

    def move_up():
        item = frames_list.currentItem()
        if item is None:
            return
        idx = int(item.data(Qt.UserRole))
        if idx > 0:
            st["frames"][idx - 1], st["frames"][idx] = \
                st["frames"][idx], st["frames"][idx - 1]
            refresh_list()
            frames_list.setCurrentRow(idx - 1)

    def move_down():
        item = frames_list.currentItem()
        if item is None:
            return
        idx = int(item.data(Qt.UserRole))
        if idx < len(st["frames"]) - 1:
            st["frames"][idx + 1], st["frames"][idx] = \
                st["frames"][idx], st["frames"][idx + 1]
            refresh_list()
            frames_list.setCurrentRow(idx + 1)

    # ---- Предпросмотр ----
    def on_list_click(item):
        idx = int(item.data(Qt.UserRole))
        st["preview_index"] = idx
        show_frame(idx)

    def toggle_play():
        if not st["frames"]:
            return
        if st["playing"]:
            anim_timer.stop()
            st["playing"] = False
            play_anim_btn.setText("▶  Проиграть предпросмотр")
        else:
            anim_timer.start(delay_spin.value())
            st["playing"] = True
            play_anim_btn.setText("⏸  Остановить")

    # ---- Генерация GIF ----
    def parse_size() -> tuple:
        idx = size_combo.currentIndex()
        sizes = [
            (128, 128), (256, 256), (320, 240), (480, 360),
            (512, 512), (640, 480), None,
        ]
        if idx == 6 and st["frames"]:
            img = st["frames"][0][2]
            return img.width(), img.height()
        return sizes[idx] if sizes[idx] else (320, 240)

    def parse_loop() -> int:
        idx = loop_combo.currentIndex()
        return [0, 1, 2, 3, 5, 10][idx]

    def make_gif():
        if not st["frames"]:
            QMessageBox.warning(root, "GIF-мастер", "Сначала добавь кадры.")
            return
        if len(st["frames"]) < 2:
            QMessageBox.information(root, "GIF-мастер",
                "Для анимации нужно минимум 2 кадра.")
            return

        status_lbl.setText("Генерация GIF…")
        QTimer.singleShot(100, do_make_gif)

    def do_make_gif():
        try:
            w, h = parse_size()
            delay = delay_spin.value()
            loop = parse_loop()

            writer = GIFWriter(w, h, delay_ms=delay, loop=loop)
            for path, name, img in st["frames"]:
                writer.add_frame(img)

            data = writer.to_bytes()
            if not data:
                raise RuntimeError("GIF получился пустой")

            st["last_gif_bytes"] = data

            # Показываем размер
            size_kb = len(data) / 1024
            status_lbl.setText(
                f"✓ GIF создан: {w}×{h}, {len(st['frames'])} кадров, "
                f"{size_kb:.1f} КБ")

            # Уведомление
            d = _get_desktop(root)
            if d and hasattr(d, "notifications"):
                d.notifications.push("GIF готов",
                    f"{len(st['frames'])} кадров, {size_kb:.1f} КБ")
        except Exception as e:
            status_lbl.setText(f"⚠ Ошибка: {e}")
            QMessageBox.warning(root, "Ошибка генерации", str(e))

    # ---- Сохранение в VFS ----
    def save_gif():
        if st["last_gif_bytes"] is None:
            QMessageBox.information(root, "GIF-мастер",
                "Сначала нажми «Создать GIF».")
            return
        if vfs is None:
            return

        name, ok = QInputDialog.getText(
            root, "Сохранить GIF",
            "Имя файла (без .gif):",
            text=f"anim_{int(time.time())}")
        if not ok or not name.strip():
            return
        name = name.strip()
        if not name.endswith(".gif"):
            name += ".gif"

        path = f"{GIF_OUT_DIR}/{name}"
        base, dot, ext = name.partition(".")
        n = 1
        while vfs.exists(path):
            path = f"{GIF_OUT_DIR}/{base}_{n}.{dot}{ext}"
            n += 1

        try:
            vfs.mkdir(GIF_OUT_DIR)
            vfs.write_bytes(path, st["last_gif_bytes"])
            status_lbl.setText(f"✓ Сохранён: {path}")

            d = _get_desktop(root)
            if d and hasattr(d, "notifications"):
                d.notifications.push("GIF сохранён", path)
        except Exception as e:
            QMessageBox.warning(root, "Ошибка", str(e))

    # ---- Связи ----
    add_btn.clicked.connect(add_frames)
    clear_btn.clicked.connect(clear_frames)
    del_btn.clicked.connect(remove_current)
    up_btn.clicked.connect(move_up)
    down_btn.clicked.connect(move_down)
    frames_list.itemClicked.connect(on_list_click)
    play_anim_btn.clicked.connect(toggle_play)
    make_btn.clicked.connect(make_gif)
    save_btn.clicked.connect(save_gif)

    # При смене задержки — если играет, перезапускаем таймер
    def on_delay_changed(v):
        if st["playing"]:
            anim_timer.start(v)

    delay_spin.valueChanged.connect(on_delay_changed)

    # Контекстное меню списка
    def show_context_menu(pos):
        item = frames_list.itemAt(pos)
        if item is None:
            return
        menu = make_menu(frames_list)
        idx = int(item.data(Qt.UserRole))

        a_preview = menu.addAction("Показать кадр")
        a_preview.triggered.connect(lambda: show_frame(idx))

        menu.addSeparator()

        a_up = menu.addAction("▲ Вверх")
        a_up.triggered.connect(move_up)
        a_down = menu.addAction("▼ Вниз")
        a_down.triggered.connect(move_down)

        menu.addSeparator()

        a_del = menu.addAction("✕ Убрать кадр")
        a_del.triggered.connect(remove_current)

        menu.exec(frames_list.mapToGlobal(pos))

    frames_list.setContextMenuPolicy(Qt.CustomContextMenu)
    frames_list.customContextMenuRequested.connect(show_context_menu)

    # ---- Стартовое состояние ----
    refresh_list()

    return root