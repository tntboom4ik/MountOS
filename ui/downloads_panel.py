"""
MountOS — Панель загрузок.

Выезжающая панель (как в браузерах) со списком всех загрузок:
  • Активные с прогресс-барами и скоростью
  • Завершённые с кнопкой «Открыть»
  • Ошибки с причиной
  • Кнопки: открыть, папка, удалить, повторить
  • Кнопка «Очистить завершённые»
  • Статистика сверху

Открывается: Ctrl+J или через кнопку в верхней панели.

API:
    from ui.downloads_panel import DownloadsPanel
    panel = DownloadsPanel(host)
    panel.toggle()
"""

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                                QPushButton, QScrollArea, QFrame, QProgressBar,
                                QMenu, QMessageBox, QGraphicsDropShadowEffect)
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QPoint
from PySide6.QtGui import QColor, QIcon, QAction

from ui.icons import get_icon
from ui.settings_state import state
from ui.context_menu import make_menu
from system.downloads_manager import (downloads, DownloadsManager,
                                       STATUS_ACTIVE, STATUS_DONE,
                                       STATUS_ERROR, STATUS_PAUSED,
                                       STATUS_CANCELLED)


PANEL_WIDTH = 420
PANEL_MARGIN = 12


# ============================================================
#  Карточка одной загрузки
# ============================================================

class DownloadCard(QWidget):
    """Карточка одного файла в списке загрузок."""

    def __init__(self, item: dict, panel, parent=None):
        super().__init__(parent)
        self.item_id = item.get("id", 0)
        self.panel = panel
        self.setFixedHeight(86)
        self.setStyleSheet("""
            DownloadCard {
                background: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 12px;
            }
            DownloadCard:hover {
                background: rgba(255, 255, 255, 0.08);
            }
        """)

        h = QHBoxLayout(self)
        h.setContentsMargins(12, 10, 12, 10)
        h.setSpacing(12)

        # ---- Иконка ----
        icon_lbl = QLabel()
        icon_lbl.setFixedSize(40, 40)
        icon_lbl.setAlignment(Qt.AlignCenter)
        icon_lbl.setPixmap(get_icon("files", 32, "#FFFFFF"))
        icon_lbl.setStyleSheet("background: transparent; border: none;")
        h.addWidget(icon_lbl)

        # ---- Текст + прогресс ----
        col = QVBoxLayout()
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(4)

        # Имя файла
        name = item.get("name", "файл")
        if len(name) > 42:
            name = name[:40] + "…"
        name_lbl = QLabel(name)
        name_lbl.setStyleSheet("""
            color: white;
            font-size: 13px;
            font-weight: 600;
            background: transparent;
            border: none;
        """)
        col.addWidget(name_lbl)

        # Прогресс-бар (для активных)
        status = item.get("status", STATUS_DONE)
        if status == STATUS_ACTIVE:
            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setValue(downloads().progress_percent(self.item_id))
            bar.setTextVisible(False)
            bar.setFixedHeight(6)
            bar.setStyleSheet("""
                QProgressBar {
                    background: rgba(255,255,255,0.10);
                    border: none;
                    border-radius: 3px;
                }
                QProgressBar::chunk {
                    background: #6EC6FF;
                    border-radius: 3px;
                }
            """)
            col.addWidget(bar)

        # Статистика
        info_text = self._info_text(item)
        info = QLabel(info_text)
        info.setStyleSheet("""
            color: rgba(255,255,255,0.55);
            font-size: 11px;
            background: transparent;
            border: none;
        """)
        info.setWordWrap(True)
        col.addWidget(info)

        h.addLayout(col, 1)

        # ---- Кнопки справа ----
        btn_col = QVBoxLayout()
        btn_col.setContentsMargins(0, 0, 0, 0)
        btn_col.setSpacing(4)

        if status == STATUS_DONE:
            open_btn = self._small_btn("Открыть", accent=True)
            open_btn.clicked.connect(lambda: self._open_file())
            btn_col.addWidget(open_btn)

        # Кнопка «...» для меню
        menu_btn = self._small_btn("⋯")
        menu_btn.setFixedWidth(32)
        menu_btn.clicked.connect(self._show_menu)
        btn_col.addWidget(menu_btn)

        h.addLayout(btn_col)

        # Правый клик — меню тоже
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(
            lambda pos: self._show_menu_at(self.mapToGlobal(pos)))

    # ------------------------------------------------------------

    def _info_text(self, item: dict) -> str:
        status = item.get("status", STATUS_DONE)
        size = item.get("size", 0)
        done = item.get("downloaded", 0)

        if status == STATUS_ACTIVE:
            pct = downloads().progress_percent(self.item_id)
            speed = downloads().current_speed(self.item_id)
            if size > 0:
                return (f"{pct}%  ·  {DownloadsManager.fmt_size(done)} / "
                        f"{DownloadsManager.fmt_size(size)}  ·  "
                        f"{DownloadsManager.fmt_speed(speed)}")
            return f"{DownloadsManager.fmt_size(done)}  ·  {DownloadsManager.fmt_speed(speed)}"

        if status == STATUS_DONE:
            time_ago = DownloadsManager.time_ago(item.get("finished_at", 0))
            return f"✓ Завершено  ·  {DownloadsManager.fmt_size(size)}  ·  {time_ago}"

        if status == STATUS_ERROR:
            err = item.get("error", "неизвестная ошибка")
            if len(err) > 50:
                err = err[:48] + "…"
            return f"⚠ {err}"

        if status == STATUS_PAUSED:
            return f"⏸ Пауза  ·  {DownloadsManager.fmt_size(done)}"

        if status == STATUS_CANCELLED:
            return "✕ Отменено"

        return "—"

    def _small_btn(self, text: str, accent: bool = False) -> QPushButton:
        b = QPushButton(text)
        b.setCursor(Qt.PointingHandCursor)
        b.setFixedHeight(28)
        b.setMinimumWidth(70)
        if accent:
            b.setStyleSheet("""
                QPushButton {
                    background: rgba(110,198,255,0.25);
                    color: white;
                    border: 1px solid rgba(110,198,255,0.60);
                    border-radius: 8px;
                    font-size: 11px;
                    padding: 3px 10px;
                }
                QPushButton:hover { background: rgba(110,198,255,0.45); }
            """)
        else:
            b.setStyleSheet("""
                QPushButton {
                    background: rgba(255,255,255,0.08);
                    color: white;
                    border: 1px solid rgba(255,255,255,0.12);
                    border-radius: 8px;
                    font-size: 12px;
                    padding: 3px 8px;
                }
                QPushButton:hover { background: rgba(255,255,255,0.18); }
            """)
        return b

    # ------------------------------------------------------------
    #  Действия
    # ------------------------------------------------------------

    def _open_file(self):
        item = downloads().get(self.item_id)
        if item is None:
            return
        path = item.get("path", "")
        if not path:
            return
        # Открываем через Desktop
        d = self.panel._get_host_desktop()
        if d and hasattr(d, "open_file"):
            d.open_file(path)

    def _show_menu(self):
        btn = self.sender()
        if btn:
            self._show_menu_at(btn.mapToGlobal(btn.rect().bottomLeft()))
        else:
            self._show_menu_at(self.mapToGlobal(self.rect().center()))

    def _show_menu_at(self, global_pos):
        item = downloads().get(self.item_id)
        if item is None:
            return

        menu = make_menu(self)
        status = item.get("status", STATUS_DONE)

        # Открыть файл
        if status == STATUS_DONE and item.get("path"):
            a_open = menu.addAction("Открыть файл")
            a_open.triggered.connect(self._open_file)

        # Открыть в проводнике
        if item.get("path"):
            a_folder = menu.addAction("Показать в проводнике")
            a_folder.triggered.connect(self._open_in_folder)

        menu.addSeparator()

        # Копировать URL
        if item.get("url"):
            a_url = menu.addAction("Копировать URL")
            a_url.triggered.connect(self._copy_url)

        # Повторить
        if status in (STATUS_ERROR, STATUS_CANCELLED):
            a_retry = menu.addAction("Повторить")
            a_retry.triggered.connect(self._retry)

        menu.addSeparator()

        # Удалить из истории
        a_del = menu.addAction("Удалить из списка")
        a_del.triggered.connect(lambda: downloads().remove(self.item_id))

        # Удалить файл
        if item.get("path") and downloads().get(self.item_id):
            a_del_file = menu.addAction("Удалить файл с диска")
            a_del_file.triggered.connect(self._delete_file)

        menu.exec(global_pos)

    def _open_in_folder(self):
        item = downloads().get(self.item_id)
        if item is None:
            return
        d = self.panel._get_host_desktop()
        if d and hasattr(d, "open_app"):
            d.open_app("files")

    def _copy_url(self):
        item = downloads().get(self.item_id)
        if item and item.get("url"):
            from PySide6.QtWidgets import QApplication
            QApplication.clipboard().setText(item["url"])

    def _retry(self):
        item = downloads().get(self.item_id)
        if item is None:
            return
        url = item.get("url", "")
        if url:
            downloads().download_url(url)

    def _delete_file(self):
        ans = QMessageBox.question(
            self, "Удалить файл",
            "Удалить файл с диска?",
            QMessageBox.Yes | QMessageBox.No)
        if ans == QMessageBox.Yes:
            downloads().remove(self.item_id, delete_file=True)


# ============================================================
#  Панель загрузок
# ============================================================

class DownloadsPanel(QWidget):
    """Выезжающая панель со списком загрузок."""

    def __init__(self, host: QWidget):
        super().__init__(host)
        self.host = host
        self.setFixedWidth(PANEL_WIDTH)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._visible = False
        self.hide()

        # ---- Внешний контейнер ----
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, PANEL_MARGIN, PANEL_MARGIN, PANEL_MARGIN)
        outer.setSpacing(0)

        card = QWidget(self)
        card.setObjectName("dlCard")
        card.setStyleSheet("""
            QWidget#dlCard {
                background: rgba(22, 28, 44, 0.97);
                border: 1px solid rgba(255,255,255,0.12);
                border-radius: 20px;
            }
        """)
        outer.addWidget(card)

        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(60)
        shadow.setOffset(-8, 8)
        shadow.setColor(QColor(0, 0, 0, 200))
        card.setGraphicsEffect(shadow)

        cl = QVBoxLayout(card)
        cl.setContentsMargins(16, 16, 16, 16)
        cl.setSpacing(12)

        # ---- Заголовок ----
        header = QHBoxLayout()
        title = QLabel("Загрузки")
        title.setStyleSheet("""
            color: white;
            font-size: 16px;
            font-weight: 600;
        """)
        header.addWidget(title)

        self.stats_lbl = QLabel("—")
        self.stats_lbl.setStyleSheet("""
            color: rgba(255,255,255,0.50);
            font-size: 11px;
            padding-left: 8px;
        """)
        header.addWidget(self.stats_lbl)

        header.addStretch(1)

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(28, 28)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255,255,255,0.06);
                color: rgba(255,255,255,0.75);
                border: 1px solid rgba(255,255,255,0.10);
                border-radius: 8px;
                font-size: 13px;
            }
            QPushButton:hover {
                background: rgba(255,107,138,0.35);
                color: white;
            }
        """)
        close_btn.clicked.connect(self.hide_panel)
        header.addWidget(close_btn)

        cl.addLayout(header)

        # ---- Кнопки действий ----
        actions = QHBoxLayout()
        actions.setSpacing(8)

        open_folder_btn = QPushButton("Открыть папку")
        open_folder_btn.setCursor(Qt.PointingHandCursor)
        open_folder_btn.setFixedHeight(32)
        open_folder_btn.setStyleSheet(self._action_btn_style())
        open_folder_btn.clicked.connect(self._open_downloads_folder)
        actions.addWidget(open_folder_btn)

        clear_btn = QPushButton("Очистить")
        clear_btn.setCursor(Qt.PointingHandCursor)
        clear_btn.setFixedHeight(32)
        clear_btn.setStyleSheet(self._action_btn_style(danger=True))
        clear_btn.clicked.connect(self._clear_finished)
        actions.addWidget(clear_btn)

        actions.addStretch(1)
        cl.addLayout(actions)

        # ---- Список ----
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
            QScrollBar:vertical {
                background: transparent; width: 6px; margin: 2px;
            }
            QScrollBar::handle:vertical {
                background: rgba(255,255,255,0.20);
                border-radius: 3px; min-height: 24px;
            }
            QScrollBar::handle:vertical:hover {
                background: rgba(255,255,255,0.35);
            }
            QScrollBar::add-line, QScrollBar::sub-line { height: 0; }
        """)

        self._holder = QWidget()
        self._holder.setStyleSheet("background: transparent;")
        self._list = QVBoxLayout(self._holder)
        self._list.setContentsMargins(0, 0, 0, 0)
        self._list.setSpacing(8)
        self._list.addStretch(1)
        self.scroll.setWidget(self._holder)
        cl.addWidget(self.scroll, 1)

        # Empty label
        self.empty_lbl = QLabel("Загрузок нет")
        self.empty_lbl.setAlignment(Qt.AlignCenter)
        self.empty_lbl.setStyleSheet("""
            color: rgba(255,255,255,0.40);
            font-size: 13px;
            padding: 60px 20px;
            background: transparent;
        """)
        self.empty_lbl.hide()

        # ---- Позиционирование ----
        self._reposition()

        # ---- Подписки на изменения ----
        downloads().changed.connect(self._on_changed)

        # ---- Автообновление прогрессов ----
        self._update_timer = QTimer(self)
        self._update_timer.timeout.connect(self._refresh_if_visible)
        self._update_timer.start(1500)

    def _action_btn_style(self, danger: bool = False):
        if danger:
            return """
                QPushButton {
                    background: rgba(255,107,138,0.15);
                    color: #FFA0B4;
                    border: 1px solid rgba(255,107,138,0.40);
                    border-radius: 9px;
                    padding: 6px 14px;
                    font-size: 11px;
                }
                QPushButton:hover {
                    background: rgba(255,107,138,0.35);
                    color: white;
                }
            """
        return """
            QPushButton {
                background: rgba(255,255,255,0.06);
                color: rgba(255,255,255,0.85);
                border: 1px solid rgba(255,255,255,0.10);
                border-radius: 9px;
                padding: 6px 14px;
                font-size: 11px;
            }
            QPushButton:hover {
                background: rgba(255,255,255,0.18);
                color: white;
            }
        """

    # ------------------------------------------------------------
    #  Позиционирование
    # ------------------------------------------------------------

    def _reposition(self):
        h = self.host.height()
        self.setFixedHeight(min(660, h - 2 * PANEL_MARGIN))
        self._hidden_x = self.host.width() + 10
        self._shown_x = self.host.width() - PANEL_WIDTH
        self._y = PANEL_MARGIN

        if self._visible:
            self.move(self._shown_x, self._y)
        else:
            self.move(self._hidden_x, self._y)

    def resizeEvent(self, e):
        self._reposition()
        super().resizeEvent(e)

    # ------------------------------------------------------------
    #  Показ / скрытие
    # ------------------------------------------------------------

    def show_panel(self):
        if self._visible:
            return
        self._reposition()
        self._refresh()
        self.show()
        self.raise_()

        anim = QPropertyAnimation(self, b"pos")
        anim.setDuration(240)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.setStartValue(QPoint(self._hidden_x, self._y))
        anim.setEndValue(QPoint(self._shown_x, self._y))
        anim.start()
        self._anim = anim
        self._visible = True

    def hide_panel(self):
        if not self._visible:
            return
        anim = QPropertyAnimation(self, b"pos")
        anim.setDuration(200)
        anim.setEasingCurve(QEasingCurve.InCubic)
        anim.setStartValue(QPoint(self._shown_x, self._y))
        anim.setEndValue(QPoint(self._hidden_x, self._y))
        anim.finished.connect(self._after_hide)
        anim.start()
        self._anim = anim
        self._visible = False

    def _after_hide(self):
        if not self._visible:
            self.hide()

    def toggle(self):
        if self._visible:
            self.hide_panel()
        else:
            self.show_panel()

    # ------------------------------------------------------------
    #  Обновление списка
    # ------------------------------------------------------------

    def _refresh_if_visible(self):
        if self._visible:
            self._refresh()

    def _on_changed(self):
        if self._visible:
            self._refresh()

    def _refresh(self):
        # Очистка
        for i in reversed(range(self._list.count())):
            it = self._list.itemAt(i)
            w = it.widget() if it else None
            if w and w is not self.empty_lbl:
                w.setParent(None)

        self.empty_lbl.setParent(None)

        items = downloads().list()

        if not items:
            self._list.insertWidget(0, self.empty_lbl)
            self.empty_lbl.show()
        else:
            self.empty_lbl.hide()
            for item in items:
                card = DownloadCard(item, self)
                self._list.insertWidget(0, card)

        # Статистика
        stats = downloads().stats()
        self.stats_lbl.setText(
            f"({stats['done']} завершено, {stats['active']} активно)")

    # ------------------------------------------------------------
    #  Действия
    # ------------------------------------------------------------

    def _open_downloads_folder(self):
        d = self._get_host_desktop()
        if d and hasattr(d, "open_app"):
            d.open_app("files")

    def _clear_finished(self):
        if not downloads().finished():
            QMessageBox.information(self, "Загрузки",
                                     "Нет завершённых загрузок.")
            return
        ans = QMessageBox.question(
            self, "Очистить историю",
            "Удалить все завершённые записи из истории?\n"
            "(файлы останутся на диске)",
            QMessageBox.Yes | QMessageBox.No)
        if ans == QMessageBox.Yes:
            removed = downloads().clear_finished(delete_files=False)
            print(f"[Downloads] очищено записей: {removed}")

    # ------------------------------------------------------------
    #  Вспомогательные
    # ------------------------------------------------------------

    def _get_host_desktop(self):
        p = self.host
        while p is not None:
            if hasattr(p, "open_app") and hasattr(p, "notifications"):
                return p
            p = p.parent() if hasattr(p, "parent") else None
        from PySide6.QtWidgets import QApplication
        for top in QApplication.topLevelWidgets():
            if hasattr(top, "open_app") and hasattr(top, "notifications"):
                return top
        return None