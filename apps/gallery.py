"""
MountOS — Галерея.
Просмотр изображений из VFS с зумом, навигацией и слайдшоу.
"""
import os
import random
from PySide6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QLabel,
                                QPushButton, QListWidget, QListWidgetItem,
                                QFileDialog, QMessageBox, QScrollArea,
                                QFrame, QSizePolicy)
from PySide6.QtCore import Qt, QSize, QTimer, Signal, QPoint
from PySide6.QtGui import QIcon, QPixmap, QImage, QPainter, QColor, QTransform

from ui.icons import get_icon
from ui.settings_state import state
from ui.context_menu import make_menu

APP_NAME = "Галерея"
APP_ICON = "files"
APP_VERSION = "1.0"
APP_AUTHOR = "MountOS"


SUPPORTED_EXT = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp",
                 ".tiff", ".tif", ".ico", ".svg", ".ppm", ".pgm", ".xpm"}


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
#  Просмотрщик (левая область)
# ============================================================

class ImageViewer(QWidget):
    """Область просмотра одного изображения с зумом и паном."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: rgba(0,0,0,0.30); border-radius: 12px;")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self._pixmap = None         # оригинал
        self._scale = 1.0
        self._offset = QPoint(0, 0)
        self._pan_start = None
        self._pan_origin = QPoint(0, 0)
        self._placeholder = "Выбери изображение слева или открой папку"

    # ---------- Данные ----------

    def set_image(self, data: bytes, path_hint: str = ""):
        img = QImage()
        if not img.loadFromData(data):
            self._pixmap = None
            self._placeholder = f"Не удалось загрузить: {path_hint or '—'}"
            self.update()
            return False
        self._pixmap = QPixmap.fromImage(img)
        self._scale = 1.0
        self._offset = QPoint(0, 0)
        self._fit_to_window()
        self.update()
        return True

    def clear_image(self, message: str = ""):
        self._pixmap = None
        self._placeholder = message or "Выбери изображение слева или открой папку"
        self.update()

    def has_image(self) -> bool:
        return self._pixmap is not None

    # ---------- Зум ----------

    def zoom_in(self):
        if self._pixmap:
            self._scale = min(self._scale * 1.25, 10.0)
            self.update()

    def zoom_out(self):
        if self._pixmap:
            self._scale = max(self._scale / 1.25, 0.1)
            self.update()

    def reset_zoom(self):
        if self._pixmap:
            self._fit_to_window()
            self.update()

    def _fit_to_window(self):
        if not self._pixmap:
            return
        pw, ph = self._pixmap.width(), self._pixmap.height()
        if pw == 0 or ph == 0:
            return
        avail_w = max(self.width() - 20, 1)
        avail_h = max(self.height() - 20, 1)
        self._scale = min(avail_w / pw, avail_h / ph, 1.0)
        self._offset = QPoint(0, 0)

    # ---------- События ----------

    def resizeEvent(self, e):
        if self._pixmap and abs(self._scale - 1.0) < 0.01:
            self._fit_to_window()
        super().resizeEvent(e)

    def wheelEvent(self, e):
        if not self._pixmap:
            return
        delta = e.angleDelta().y()
        if delta > 0:
            self.zoom_in()
        else:
            self.zoom_out()
        e.accept()

    def mousePressEvent(self, e):
        if self._pixmap and e.button() == Qt.LeftButton:
            self._pan_start = e.position().toPoint()
            self._pan_origin = QPoint(self._offset)

    def mouseMoveEvent(self, e):
        if self._pixmap and self._pan_start is not None and e.buttons() & Qt.LeftButton:
            delta = e.position().toPoint() - self._pan_start
            self._offset = self._pan_origin + delta
            self.update()

    def mouseReleaseEvent(self, e):
        self._pan_start = None

    def mouseDoubleClickEvent(self, e):
        self.reset_zoom()

    # ---------- Отрисовка ----------

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.fillRect(self.rect(), QColor(0, 0, 0, 90))

        if self._pixmap is None:
            p.setPen(QColor(255, 255, 255, 120))
            p.drawText(self.rect(), Qt.AlignCenter, self._placeholder)
            return

        w = int(self._pixmap.width() * self._scale)
        h = int(self._pixmap.height() * self._scale)
        x = (self.width() - w) // 2 + self._offset.x()
        y = (self.height() - h) // 2 + self._offset.y()

        p.drawPixmap(x, y, w, h, self._pixmap)


# ============================================================
#  Основное приложение
# ============================================================

def build():
    root = QWidget()
    h = QHBoxLayout(root)
    h.setContentsMargins(0, 0, 0, 0)
    h.setSpacing(0)

    # ----- Левая панель: список файлов -----
    side = QWidget()
    side.setFixedWidth(240)
    side.setStyleSheet("""
        background: rgba(255,255,255,0.04);
        border-right: 1px solid rgba(255,255,255,0.08);
    """)
    sl = QVBoxLayout(side)
    sl.setContentsMargins(12, 14, 12, 14)
    sl.setSpacing(8)

    header = QLabel("Изображения")
    header.setStyleSheet("color: white; font-size: 14px; font-weight: 600; padding: 2px 4px;")
    sl.addWidget(header)

    # Кнопки: обновить / открыть папку
    btn_row = QHBoxLayout()
    btn_row.setSpacing(6)

    refresh_btn = QPushButton()
    refresh_btn.setIcon(QIcon(get_icon("back", 16, "#FFFFFF")))
    refresh_btn.setFixedSize(30, 30)
    refresh_btn.setToolTip("Обновить")
    refresh_btn.setCursor(Qt.PointingHandCursor)
    refresh_btn.setStyleSheet(_icon_btn_style())
    btn_row.addWidget(refresh_btn)

    folder_btn = QPushButton("  Все изображения")
    folder_btn.setCursor(Qt.PointingHandCursor)
    folder_btn.setFixedHeight(30)
    folder_btn.setStyleSheet("""
        QPushButton {
            background: rgba(255,255,255,0.08);
            color: white;
            border: 1px solid rgba(255,255,255,0.14);
            border-radius: 8px;
            padding: 4px 10px;
            text-align: left;
            font-size: 11px;
        }
        QPushButton:hover { background: rgba(255,255,255,0.18); }
    """)
    btn_row.addWidget(folder_btn, 1)

    sl.addLayout(btn_row)

    # Список файлов
    listing = QListWidget()
    listing.setStyleSheet("""
        QListWidget {
            background: rgba(0,0,0,0.18);
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 10px;
            color: white;
            font-size: 12px;
            outline: none;
            padding: 4px;
        }
        QListWidget::item {
            padding: 6px 8px;
            border-radius: 6px;
        }
        QListWidget::item:hover { background: rgba(255,255,255,0.08); }
        QListWidget::item:selected { background: rgba(110,198,255,0.30); }
    """)
    listing.setIconSize(QSize(24, 24))
    sl.addWidget(listing, 1)

    # Импорт с ПК
    import_btn = QPushButton("  Импортировать с ПК")
    import_btn.setIcon(QIcon(get_icon("plus", 16, "#6EC6FF")))
    import_btn.setCursor(Qt.PointingHandCursor)
    import_btn.setFixedHeight(34)
    import_btn.setStyleSheet("""
        QPushButton {
            background: rgba(110,198,255,0.18);
            color: white;
            border: 1px solid rgba(110,198,255,0.55);
            border-radius: 10px;
            padding: 6px 12px;
            text-align: left;
            font-size: 12px;
        }
        QPushButton:hover { background: rgba(110,198,255,0.35); }
    """)
    sl.addWidget(import_btn)

    h.addWidget(side)

    # ----- Правая область: просмотр + нижняя панель -----
    right = QWidget()
    rl = QVBoxLayout(right)
    rl.setContentsMargins(14, 14, 14, 14)
    rl.setSpacing(10)

    # Заголовок с именем файла
    file_name_lbl = QLabel("—")
    file_name_lbl.setStyleSheet("""
        color: white;
        font-size: 13px;
        font-weight: 600;
        padding: 2px 4px;
    """)
    file_name_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
    rl.addWidget(file_name_lbl)

    # Просмотрщик
    viewer = ImageViewer()
    rl.addWidget(viewer, 1)

    # Нижняя панель управления
    controls = QWidget()
    controls.setFixedHeight(48)
    controls.setStyleSheet("""
        background: rgba(255,255,255,0.04);
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 12px;
    """)
    cl = QHBoxLayout(controls)
    cl.setContentsMargins(10, 6, 10, 6)
    cl.setSpacing(6)

    prev_btn = QPushButton("◀")
    prev_btn.setFixedSize(36, 36)
    prev_btn.setToolTip("Предыдущее (←)")
    prev_btn.setCursor(Qt.PointingHandCursor)
    prev_btn.setStyleSheet(_ctrl_btn_style())
    cl.addWidget(prev_btn)

    next_btn = QPushButton("▶")
    next_btn.setFixedSize(36, 36)
    next_btn.setToolTip("Следующее (→)")
    next_btn.setCursor(Qt.PointingHandCursor)
    next_btn.setStyleSheet(_ctrl_btn_style())
    cl.addWidget(next_btn)

    cl.addSpacing(12)

    zoom_out_btn = QPushButton("−")
    zoom_out_btn.setFixedSize(36, 36)
    zoom_out_btn.setToolTip("Уменьшить (Ctrl+-)")
    zoom_out_btn.setCursor(Qt.PointingHandCursor)
    zoom_out_btn.setStyleSheet(_ctrl_btn_style())
    cl.addWidget(zoom_out_btn)

    zoom_fit_btn = QPushButton("⤢")
    zoom_fit_btn.setFixedSize(36, 36)
    zoom_fit_btn.setToolTip("По размеру окна (двойной клик)")
    zoom_fit_btn.setCursor(Qt.PointingHandCursor)
    zoom_fit_btn.setStyleSheet(_ctrl_btn_style())
    cl.addWidget(zoom_fit_btn)

    zoom_in_btn = QPushButton("+")
    zoom_in_btn.setFixedSize(36, 36)
    zoom_in_btn.setToolTip("Увеличить (Ctrl++)")
    zoom_in_btn.setCursor(Qt.PointingHandCursor)
    zoom_in_btn.setStyleSheet(_ctrl_btn_style())
    cl.addWidget(zoom_in_btn)

    cl.addSpacing(12)

    slideshow_btn = QPushButton("▶ Слайдшоу")
    slideshow_btn.setCursor(Qt.PointingHandCursor)
    slideshow_btn.setFixedHeight(36)
    slideshow_btn.setStyleSheet("""
        QPushButton {
            background: rgba(110,198,255,0.18);
            color: white;
            border: 1px solid rgba(110,198,255,0.55);
            border-radius: 10px;
            padding: 6px 16px;
            font-size: 12px;
        }
        QPushButton:hover { background: rgba(110,198,255,0.35); }
    """)
    cl.addWidget(slideshow_btn)

    cl.addStretch(1)

    info_lbl = QLabel("")
    info_lbl.setStyleSheet("color: rgba(255,255,255,0.55); font-size: 11px;")
    cl.addWidget(info_lbl)

    rl.addWidget(controls)

    h.addWidget(right, 1)

    # ============================================================
    #  Логика
    # ============================================================

    state_obj = {
        "items": [],       # список {name, path}
        "current": -1,
        "slideshow": False,
    }

    def scan_images():
        """Сканирует VFS на предмет изображений."""
        vfs = _get_vfs(root)
        if vfs is None:
            return []
        found = []

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
                    ext = os.path.splitext(it["name"])[1].lower()
                    if ext in SUPPORTED_EXT:
                        found.append({"name": it["name"], "path": it["path"]})
        walk("/")
        return found

    def refresh_list(select_path=None):
        state_obj["items"] = scan_images()
        listing.clear()

        for idx, it in enumerate(state_obj["items"]):
            item = QListWidgetItem(QIcon(get_icon("files", 22, state().get("accent"))),
                                    it["name"])
            item.setData(Qt.UserRole, idx)
            listing.addItem(item)

        info_lbl.setText(f"{len(state_obj['items'])} изобр.")

        if select_path:
            for i, it in enumerate(state_obj["items"]):
                if it["path"] == select_path:
                    listing.setCurrentRow(i)
                    _show_index(i)
                    return

        if state_obj["items"] and state_obj["current"] < 0:
            listing.setCurrentRow(0)
            _show_index(0)

    def _show_index(idx: int):
        vfs = _get_vfs(root)
        if vfs is None:
            return
        items = state_obj["items"]
        if not items:
            return
        idx = max(0, min(idx, len(items) - 1))
        state_obj["current"] = idx
        it = items[idx]
        file_name_lbl.setText(it["path"])
        try:
            data = vfs.read_bytes(it["path"])
        except Exception as e:
            viewer.clear_image(f"Ошибка: {e}")
            return
        viewer.set_image(data, it["name"])
        listing.setCurrentRow(idx)

    def open_path(path: str):
        refresh_list(select_path=path)

    def next_image():
        if not state_obj["items"]:
            return
        _show_index((state_obj["current"] + 1) % len(state_obj["items"]))

    def prev_image():
        if not state_obj["items"]:
            return
        _show_index((state_obj["current"] - 1) % len(state_obj["items"]))

    def on_list_click(item):
        idx = item.data(Qt.UserRole)
        _show_index(int(idx))

    # ---- Связки ----
    listing.itemClicked.connect(on_list_click)
    next_btn.clicked.connect(next_image)
    prev_btn.clicked.connect(prev_image)
    zoom_in_btn.clicked.connect(viewer.zoom_in)
    zoom_out_btn.clicked.connect(viewer.zoom_out)
    zoom_fit_btn.clicked.connect(viewer.reset_zoom)
    refresh_btn.clicked.connect(lambda: refresh_list())
    folder_btn.clicked.connect(lambda: refresh_list())

    # ---- Импорт с ПК ----
    def import_from_pc():
        vfs = _get_vfs(root)
        if vfs is None:
            return
        files, _ = QFileDialog.getOpenFileNames(
            root, "Импортировать изображения", "",
            "Изображения (*.png *.jpg *.jpeg *.bmp *.gif *.webp *.tiff *.svg);;Все файлы (*)")
        if not files:
            return
        target_dir = "/Pictures"
        vfs.mkdir(target_dir)
        imported = 0
        for src in files:
            name = os.path.basename(src)
            try:
                with open(src, "rb") as f:
                    data = f.read()
                vfs.write_bytes(vfs.join(target_dir, name), data)
                imported += 1
            except Exception as e:
                print(f"[Gallery] импорт {name}: {e}")

        d = _get_desktop(root)
        if d:
            d.notifications.push("Импортировано",
                                 f"{imported} изображений → /Pictures")
        refresh_list()

    import_btn.clicked.connect(import_from_pc)

    # ---- Слайдшоу ----
    slideshow_timer = QTimer(root)
    slideshow_timer.setInterval(2500)

    def slideshow_tick():
        next_image()

    slideshow_timer.timeout.connect(slideshow_tick)

    def toggle_slideshow():
        if state_obj["slideshow"]:
            slideshow_timer.stop()
            state_obj["slideshow"] = False
            slideshow_btn.setText("▶ Слайдшоу")
            slideshow_btn.setStyleSheet("""
                QPushButton {
                    background: rgba(110,198,255,0.18);
                    color: white;
                    border: 1px solid rgba(110,198,255,0.55);
                    border-radius: 10px;
                    padding: 6px 16px;
                    font-size: 12px;
                }
                QPushButton:hover { background: rgba(110,198,255,0.35); }
            """)
        else:
            if len(state_obj["items"]) < 2:
                return
            slideshow_timer.start()
            state_obj["slideshow"] = True
            slideshow_btn.setText("⏸ Стоп")
            slideshow_btn.setStyleSheet("""
                QPushButton {
                    background: rgba(255,107,138,0.20);
                    color: #FFA0B4;
                    border: 1px solid rgba(255,107,138,0.50);
                    border-radius: 10px;
                    padding: 6px 16px;
                    font-size: 12px;
                }
                QPushButton:hover { background: rgba(255,107,138,0.40); color: white; }
            """)

    slideshow_btn.clicked.connect(toggle_slideshow)

    # ---- Клавиши ----
    def keyPressEvent(e):
        if e.key() == Qt.Key_Left:
            prev_image()
        elif e.key() == Qt.Key_Right:
            next_image()
        elif e.key() in (Qt.Key_Plus, Qt.Key_Equal) and e.modifiers() & Qt.ControlModifier:
            viewer.zoom_in()
        elif e.key() == Qt.Key_Minus and e.modifiers() & Qt.ControlModifier:
            viewer.zoom_out()
        elif e.key() == Qt.Key_Space:
            toggle_slideshow()
        else:
            super(type(root), root).keyPressEvent(e)

    root.keyPressEvent = keyPressEvent
    root.setFocusPolicy(Qt.StrongFocus)

    # ---- Первичная загрузка ----
    refresh_list()

    return root


# ============================================================
#  Стили
# ============================================================

def _icon_btn_style():
    return """
        QPushButton {
            background: rgba(255,255,255,0.08);
            color: white;
            border: 1px solid rgba(255,255,255,0.14);
            border-radius: 8px;
        }
        QPushButton:hover { background: rgba(255,255,255,0.20); }
        QPushButton:pressed { background: rgba(110,198,255,0.35); }
    """


def _ctrl_btn_style():
    return """
        QPushButton {
            background: rgba(255,255,255,0.06);
            color: white;
            border: 1px solid rgba(255,255,255,0.10);
            border-radius: 8px;
            font-size: 14px;
        }
        QPushButton:hover {
            background: rgba(255,255,255,0.20);
            border: 1px solid rgba(255,255,255,0.24);
        }
        QPushButton:pressed { background: rgba(110,198,255,0.35); }
    """