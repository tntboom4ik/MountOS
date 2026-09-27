"""
MountOS — Меню приложений.

Полностью переработано:
  • Фиксированный заголовок с поиском и крестиком
  • Адаптивная сетка под ширину
  • Acrylic blur через WinAPI
  • Принудительная перерисовка (защита от «призраков»)
"""
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                                QPushButton, QLineEdit, QScrollArea, QFrame,
                                QApplication, QGridLayout, QSizePolicy)
from PySide6.QtCore import (Qt, QPropertyAnimation, QEasingCurve, Signal,
                             QSize, QTimer)
from PySide6.QtGui import QIcon, QColor, QPainter

from ui.icons import get_icon
from ui.settings_state import state
from system.blur import apply_acrylic_overlay, is_supported


class AppTile(QPushButton):
    activated = Signal(str)
    context_requested = Signal(str, object)

    def __init__(self, app_id: str, name: str, icon_name: str,
                 version: str = "", builtin: bool = True, parent=None):
        super().__init__(parent)
        self.app_id = app_id
        self.icon_name = icon_name
        self.app_name = name
        self.builtin = builtin

        self.setFixedSize(140, 150)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(f"{name}\n{app_id} · v{version}"
                        + ("\n(системное)" if builtin else "\n(пользовательское)"))

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 16, 10, 12)
        lay.setSpacing(8)

        icon_wrap = QWidget(self)
        icon_wrap.setFixedSize(72, 72)
        icon_wrap.setStyleSheet("""
            QWidget {
                background: rgba(255,255,255,0.10);
                border: 1px solid rgba(255,255,255,0.16);
                border-radius: 20px;
            }
        """)
        iw = QHBoxLayout(icon_wrap)
        iw.setContentsMargins(0, 0, 0, 0)
        iw.setAlignment(Qt.AlignCenter)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(get_icon(icon_name, 40, state().get("accent")))
        icon_lbl.setStyleSheet("background: transparent; border: none;")
        iw.addWidget(icon_lbl)

        wrap_row = QHBoxLayout()
        wrap_row.addStretch(1)
        wrap_row.addWidget(icon_wrap)
        wrap_row.addStretch(1)
        lay.addLayout(wrap_row)

        name_lbl = QLabel(name)
        name_lbl.setAlignment(Qt.AlignCenter)
        name_lbl.setWordWrap(True)
        name_lbl.setStyleSheet("""
            color: white;
            font-size: 12px;
            font-weight: 500;
            background: transparent;
        """)
        lay.addWidget(name_lbl)

        lay.addStretch(1)

        self.setStyleSheet("""
            AppTile {
                background: rgba(255,255,255,0.06);
                border: 1px solid rgba(255,255,255,0.10);
                border-radius: 18px;
            }
            AppTile:hover {
                background: rgba(255,255,255,0.16);
                border: 1px solid rgba(255,255,255,0.24);
            }
            AppTile:pressed {
                background: rgba(110,198,255,0.30);
                border: 1px solid rgba(110,198,255,0.60);
            }
        """)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self.rect().contains(e.position().toPoint()):
            self.activated.emit(self.app_id)
        super().mouseReleaseEvent(e)

    def contextMenuEvent(self, e):
        self.context_requested.emit(self.app_id, e.globalPos())


class AppMenu(QWidget):
    app_launch_requested = Signal(str)
    app_delete_requested = Signal(str)
    app_install_requested = Signal()

    def __init__(self, host: QWidget):
        super().__init__(host)
        self.host = host
        self.hide()
        self._visible = False
        self._registry = None
        self._blur_applied = False

        self.setAttribute(Qt.WA_TranslucentBackground)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Верхняя панель (ФИКСИРОВАННАЯ)
        top = QWidget(self)
        top.setFixedHeight(80)
        top.setStyleSheet("""
            QWidget {
                background: rgba(20, 26, 42, 0.60);
                border-bottom: 1px solid rgba(255,255,255,0.08);
            }
        """)
        tl = QHBoxLayout(top)
        tl.setContentsMargins(30, 18, 30, 18)
        tl.setSpacing(16)

        title = QLabel("Все приложения", top)
        title.setStyleSheet("""
            color: white;
            font-size: 22px;
            font-weight: 300;
            letter-spacing: 1px;
            background: transparent;
        """)
        title.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        tl.addWidget(title)

        tl.addStretch(1)

        self.search = QLineEdit(top)
        self.search.setPlaceholderText("Поиск приложений…")
        self.search.setFixedWidth(280)
        self.search.setFixedHeight(40)
        self.search.setStyleSheet("""
            QLineEdit {
                background: rgba(255,255,255,0.10);
                color: white;
                border: 1px solid rgba(255,255,255,0.18);
                border-radius: 12px;
                padding: 8px 14px;
                font-size: 13px;
            }
            QLineEdit:focus {
                border: 1px solid rgba(110,198,255,0.65);
                background: rgba(255,255,255,0.14);
            }
        """)
        self.search.textChanged.connect(self._filter)
        tl.addWidget(self.search)

        close_btn = QPushButton("✕", top)
        close_btn.setFixedSize(40, 40)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255,255,255,0.08);
                color: rgba(255,255,255,0.85);
                border: 1px solid rgba(255,255,255,0.14);
                border-radius: 12px;
                font-size: 15px;
            }
            QPushButton:hover {
                background: rgba(255,107,138,0.35);
                color: white;
                border: 1px solid rgba(255,107,138,0.60);
            }
        """)
        close_btn.clicked.connect(self.hide_menu)
        tl.addWidget(close_btn)

        root.addWidget(top)

        # Скролл
        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
            QScrollBar:vertical {
                background: transparent; width: 10px; margin: 6px;
            }
            QScrollBar::handle:vertical {
                background: rgba(255,255,255,0.25);
                border-radius: 5px; min-height: 40px;
            }
            QScrollBar::handle:vertical:hover {
                background: rgba(110,198,255,0.55);
            }
            QScrollBar::add-line, QScrollBar::sub-line { height: 0; }
        """)

        self._holder = QWidget()
        self._holder.setStyleSheet("background: transparent;")
        self._grid = QGridLayout(self._holder)
        self._grid.setContentsMargins(40, 30, 40, 40)
        self._grid.setHorizontalSpacing(14)
        self._grid.setVerticalSpacing(14)
        self._grid.setAlignment(Qt.AlignTop | Qt.AlignHCenter)

        self.scroll.setWidget(self._holder)
        root.addWidget(self.scroll, 1)

        self.empty_lbl = QLabel("Ничего не найдено", self._holder)
        self.empty_lbl.setAlignment(Qt.AlignCenter)
        self.empty_lbl.setStyleSheet("""
            color: rgba(255,255,255,0.45);
            font-size: 15px;
            padding: 60px;
            background: transparent;
        """)
        self.empty_lbl.hide()

    # ------------------------------------------------------------

    def set_registry(self, registry):
        self._registry = registry

    def show_menu(self):
        if self._visible:
            return

        self.setGeometry(self.host.rect())
        self.update()
        self.repaint()

        self.show()
        self.raise_()
        self.activateWindow()
        self.setFocus()

        QTimer.singleShot(30, self._try_apply_blur)
        QTimer.singleShot(50, self._rebuild)

        self.search.clear()
        QTimer.singleShot(80, self.search.setFocus)

        self.setWindowOpacity(0.0)
        anim = QPropertyAnimation(self, b"windowOpacity")
        anim.setDuration(220)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.start()
        self._anim = anim
        self._visible = True

    def _try_apply_blur(self):
        if self._blur_applied:
            return
        if not is_supported():
            return
        try:
            ok = apply_acrylic_overlay(self, tint_hex="#0A0E1A", tint_alpha=0xCC)
            self._blur_applied = ok
        except Exception as e:
            print(f"[AppMenu] blur: {e}")

    def hide_menu(self):
        if not self._visible:
            return
        anim = QPropertyAnimation(self, b"windowOpacity")
        anim.setDuration(180)
        anim.setEasingCurve(QEasingCurve.InCubic)
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        anim.finished.connect(self._after_hide)
        anim.start()
        self._anim = anim
        self._visible = False

    def _after_hide(self):
        if not self._visible:
            self.hide()
            if self.host:
                self.host.update()

    def toggle(self):
        if self._visible:
            self.hide_menu()
        else:
            self.show_menu()

    # ------------------------------------------------------------

    def _clear_grid(self):
        while self._grid.count():
            it = self._grid.takeAt(0)
            w = it.widget()
            if w and w is not self.empty_lbl:
                w.setParent(None)

    def _tiles_per_row(self) -> int:
        w = self.width() - 80
        n = max(1, w // (140 + 14))
        return n

    def _rebuild(self):
        self._clear_grid()
        self.empty_lbl.setParent(None)

        if self._registry is None:
            self._grid.addWidget(self.empty_lbl, 0, 0)
            self.empty_lbl.show()
            return

        apps = self._registry.apps
        builtin = [(k, v) for k, v in apps.items() if v.builtin]
        custom = [(k, v) for k, v in apps.items() if not v.builtin]
        builtin.sort(key=lambda kv: kv[1].name.lower())
        custom.sort(key=lambda kv: kv[1].name.lower())

        per_row = self._tiles_per_row()
        row = [0]

        def add_section(title_text: str, items: list):
            if not items:
                return

            lbl = QLabel(title_text.upper())
            lbl.setStyleSheet("""
                color: rgba(255,255,255,0.50);
                font-size: 11px;
                font-weight: 700;
                letter-spacing: 2px;
                background: transparent;
                padding: 14px 4px 4px 4px;
            """)
            self._grid.addWidget(lbl, row[0], 0, 1, per_row)
            row[0] += 1

            col = 0
            for app_id, info in items:
                tile = AppTile(
                    app_id=app_id,
                    name=info.name,
                    icon_name=info.app_id,
                    version=info.version,
                    builtin=info.builtin,
                )
                tile.activated.connect(self._on_tile)
                tile.context_requested.connect(self._on_tile_context)
                self._grid.addWidget(tile, row[0], col)
                col += 1
                if col >= per_row:
                    col = 0
                    row[0] += 1
            if col > 0:
                row[0] += 1

        add_section("Системные", builtin)
        add_section("Пользовательские", custom)

        if not builtin and not custom:
            self._grid.addWidget(self.empty_lbl, row[0], 0, 1, per_row)
            self.empty_lbl.show()

    def _filter(self, query: str):
        self._rebuild()

        query = (query or "").strip().lower()
        if not query:
            return

        for i in range(self._grid.count()):
            it = self._grid.itemAt(i)
            w = it.widget()
            if isinstance(w, AppTile):
                text = (w.app_name + " " + w.app_id).lower()
                w.setVisible(query in text)

        has_visible = False
        for i in range(self._grid.count()):
            w = self._grid.itemAt(i).widget()
            if isinstance(w, AppTile) and w.isVisible():
                has_visible = True
                break

        if not has_visible:
            self.empty_lbl.setText("Ничего не найдено")
            if self.empty_lbl.parent() is None:
                self._grid.addWidget(self.empty_lbl, self._grid.rowCount(),
                                      0, 1, self._tiles_per_row())
            self.empty_lbl.show()

    def _on_tile(self, app_id: str):
        self.hide_menu()
        self.app_launch_requested.emit(app_id)

    def _on_tile_context(self, app_id: str, global_pos):
        from ui.context_menu import make_menu
        menu = make_menu(self)
        a_open = menu.addAction("Открыть")
        a_open.triggered.connect(lambda: self._on_tile(app_id))

        if self._registry and app_id in self._registry.apps:
            info = self._registry.apps[app_id]
            if not info.builtin:
                menu.addSeparator()
                a_del = menu.addAction("🗑  Удалить приложение")
                a_del.triggered.connect(
                    lambda: self.app_delete_requested.emit(app_id))

        menu.exec(global_pos)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.hide_menu()
        elif e.key() in (Qt.Key_Return, Qt.Key_Enter):
            if self.search.text().strip():
                apps = self._registry.apps if self._registry else {}
                q = self.search.text().strip().lower()
                for app_id, info in apps.items():
                    if q in info.name.lower() or q in app_id.lower():
                        self._on_tile(app_id)
                        return
        super().keyPressEvent(e)

    def resizeEvent(self, e):
        if self.host:
            self.setGeometry(self.host.rect())
        if self._visible:
            QTimer.singleShot(20, self._rebuild)
        super().resizeEvent(e)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if self._blur_applied:
            p.fillRect(self.rect(), QColor(8, 12, 22, 100))
        else:
            p.fillRect(self.rect(), QColor(10, 14, 26, 235))