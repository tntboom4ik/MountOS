from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout,
                                QLabel, QPushButton, QGraphicsDropShadowEffect,
                                QApplication)
from PySide6.QtCore import Qt, QPoint, QRect, QPropertyAnimation, Signal
from PySide6.QtGui import (QPainter, QColor, QPainterPath, QBrush, QPen,
                            QLinearGradient)

from ui.settings_state import state


class GlassWindow(QWidget):
    """Окно MountOS: перетаскивание, ресайз, снап к краям."""

    closed = Signal(object)
    RESIZE_MARGIN = 8

    def __init__(self, parent, title: str, content: QWidget,
                 width: int = 720, height: int = 460,
                 app_id: str = "", icon: str = "📦"):
        super().__init__(None)
        self.app_id = app_id
        self.icon = icon
        self.setWindowTitle(f"MountOS — {title}")
        self.resize(width, height)
        self.setMinimumSize(360, 240)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)

        self._drag_offset = QPoint()
        self._prev_geom = None
        self._resize_edge = None
        self._resize_start_geom = None
        self._resize_start_pos = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 30)
        outer.setSpacing(0)

        # Заголовок
        self.title_bar = QWidget(self)
        self.title_bar.setFixedHeight(48)
        self.title_bar.setCursor(Qt.SizeAllCursor)
        tb = QHBoxLayout(self.title_bar)
        tb.setContentsMargins(18, 0, 12, 0)

        self.title_label = QLabel(title)
        self.title_label.setStyleSheet("""
            color: rgba(255,255,255,0.95);
            font-size: 14px;
            font-weight: 600;
        """)
        tb.addWidget(self.title_label)
        tb.addStretch(1)

        for color, hover, action in [
            ("#FFB86C", "#FFD0A0", self.showMinimized),
            ("#6EC6FF", "#A0DEFF", self._maximize),
            ("#FF6B8A", "#FFA0B4", self.close),
        ]:
            b = QPushButton()
            b.setFixedSize(14, 14)
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet(f"""
                QPushButton {{ background: {color}; border-radius: 7px; border: none; }}
                QPushButton:hover {{ background: {hover}; }}
            """)
            b.clicked.connect(action)
            tb.addWidget(b)

        outer.addWidget(self.title_bar)

        content.setParent(self)
        outer.addWidget(content, 1)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(60)
        shadow.setOffset(0, 12)
        shadow.setColor(QColor(0, 0, 0, 180))
        self.setGraphicsEffect(shadow)

        self.setWindowOpacity(0.0)
        self.setMouseTracking(True)

        # Храним ссылку на Desktop, чтобы приложения могли её достать
        self.desktop_ref = parent
        content.desktop_ref = parent

        state().changed.connect(self._on_state)

    def _on_state(self, key, val):
        if key in ("window_opacity", "window_radius", "accent"):
            self.update()

    # ---------- Перетаскивание ----------
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            edge = self._edge_at(e.position().toPoint())
            if edge:
                self._resize_edge = edge
                self._resize_start_geom = self.geometry()
                self._resize_start_pos = e.globalPosition().toPoint()
                e.accept()
                return
            self._drag_offset = (e.globalPosition().toPoint()
                                 - self.frameGeometry().topLeft())
            e.accept()

    def mouseMoveEvent(self, e):
        pos = e.position().toPoint()
        if self._resize_edge and e.buttons() & Qt.LeftButton:
            self._do_resize(e.globalPosition().toPoint())
            e.accept()
            return

        edge = self._edge_at(pos)
        cursors = {
            "l": Qt.SizeHorCursor, "r": Qt.SizeHorCursor,
            "t": Qt.SizeVerCursor, "b": Qt.SizeVerCursor,
            "tl": Qt.SizeFDiagCursor, "br": Qt.SizeFDiagCursor,
            "tr": Qt.SizeBDiagCursor, "bl": Qt.SizeBDiagCursor,
        }
        self.setCursor(cursors.get(edge, Qt.ArrowCursor))

        if e.buttons() & Qt.LeftButton and not self._drag_offset.isNull():
            self.move(e.globalPosition().toPoint() - self._drag_offset)
            e.accept()

    def mouseReleaseEvent(self, e):
        if self._resize_edge:
            self._resize_edge = None
            self._resize_start_geom = None
        self._drag_offset = QPoint()
        self._snap_to_edges()

    # ---------- Ресайз ----------
    def _edge_at(self, pos: QPoint):
        m = self.RESIZE_MARGIN
        w, h = self.width(), self.height()
        L = pos.x() < m
        R = pos.x() > w - m
        T = pos.y() < m
        B = pos.y() > h - m
        if T and L: return "tl"
        if T and R: return "tr"
        if B and L: return "bl"
        if B and R: return "br"
        if L: return "l"
        if R: return "r"
        if T: return "t"
        if B: return "b"
        return None

    def _do_resize(self, gp):
        delta = gp - self._resize_start_pos
        g = QRect(self._resize_start_geom)
        if "l" in self._resize_edge: g.setLeft(g.left() + delta.x())
        if "r" in self._resize_edge: g.setRight(g.right() + delta.x())
        if "t" in self._resize_edge: g.setTop(g.top() + delta.y())
        if "b" in self._resize_edge: g.setBottom(g.bottom() + delta.y())
        if g.width() >= self.minimumWidth() and g.height() >= self.minimumHeight():
            self.setGeometry(g)

    def _snap_to_edges(self):
        scr = QApplication.primaryScreen().availableGeometry()
        g = self.geometry(); snap = 14
        if abs(g.left() - scr.left()) < snap: g.moveLeft(scr.left())
        if abs(g.right() - scr.right()) < snap: g.moveRight(scr.right())
        if abs(g.top() - scr.top()) < snap: g.moveTop(scr.top())
        if abs(g.bottom() - scr.bottom()) < snap: g.moveBottom(scr.bottom())
        self.setGeometry(g)

    def _maximize(self):
        if self._prev_geom is None:
            self._prev_geom = self.geometry()
            scr = QApplication.primaryScreen().availableGeometry()
            self.setGeometry(scr)
        else:
            self.setGeometry(self._prev_geom)
            self._prev_geom = None

    def closeEvent(self, e):
        self.closed.emit(self)
        super().closeEvent(e)

    # ---------- Отрисовка стекла ----------
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        rect = self.rect().adjusted(20, 20, -20, -30)
        radius = state().get("window_radius", 22)
        opacity = state().get("window_opacity", 0.92)
        alpha = int(255 * opacity)

        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)
        p.fillPath(path, QBrush(QColor(28, 34, 54, alpha)))

        pen = QPen(QColor(255, 255, 255, 50)); pen.setWidth(1)
        p.setPen(pen); p.drawPath(path)

        hl = QRect(rect.left() + 1, rect.top() + 1,
                   rect.width() - 2, rect.height() // 2)
        hl_path = QPainterPath()
        hl_path.addRoundedRect(hl, radius, radius)
        grad = QLinearGradient(0, rect.top(), 0, rect.top() + rect.height() // 2)
        grad.setColorAt(0, QColor(255, 255, 255, 30))
        grad.setColorAt(1, QColor(255, 255, 255, 0))
        p.fillPath(hl_path, QBrush(grad))