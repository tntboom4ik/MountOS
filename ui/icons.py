"""
MountOS — Векторные иконки.

Все иконки рисуются QPainter — не зависят от шрифтов и эмодзи.
Единый стиль: stroke ~7% от размера, скруглённые концы, без заливки.

Категории:
  • Система:    settings, power, terminal, taskmgr, shield, key
  • Файлы:      files, folder, file, editor, save, download, upload
  • Медиа:      music, gallery, video, camera, mic, radio
  • Интернет:   globe, browser, wifi, cloud, mail, chat
  • Утилиты:    calculator, clock, calendar, grid, search, star,
                plus, minus, close, back, forward, reload, home,
                trash, bell, check, lock, unlock

Умный подбор: если точного ключа нет — ищет по подстроке/ключевым словам.
"""
from PySide6.QtGui import QPixmap, QPainter, QColor, QPen, QBrush, QPainterPath
from PySide6.QtCore import Qt, QRectF, QPointF
import math


# ============================================================
#  Утилиты
# ============================================================

def _canvas(size):
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    return pm, p


def _pen(color, size, width_ratio=0.07):
    pen = QPen(QColor(color))
    pen.setWidthF(size * width_ratio)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    return pen


def _pen_thin(color, size):
    return _pen(color, size, 0.05)


def _pen_bold(color, size):
    return _pen(color, size, 0.09)


# ============================================================
#  СИСТЕМА
# ============================================================

def _icon_settings(size, color):
    pm, p = _canvas(size)
    s = size
    pen = _pen(color, s)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    cx, cy = s / 2, s / 2
    r_inner = s * 0.16
    r_outer = s * 0.34
    p.drawEllipse(QPointF(cx, cy), r_inner, r_inner)
    for i in range(8):
        a = math.radians(i * 45)
        x1 = cx + math.cos(a) * r_inner * 1.1
        y1 = cy + math.sin(a) * r_inner * 1.1
        x2 = cx + math.cos(a) * r_outer
        y2 = cy + math.sin(a) * r_outer
        p.drawLine(QPointF(x1, y1), QPointF(x2, y2))
    p.end()
    return pm


def _icon_power(size, color):
    pm, p = _canvas(size)
    s = size
    pen = _pen_bold(color, s)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    rect = QRectF(s * 0.22, s * 0.26, s * 0.56, s * 0.56)
    p.drawArc(rect, 60 * 16, 300 * 16)
    p.drawLine(QPointF(s * 0.5, s * 0.16), QPointF(s * 0.5, s * 0.5))
    p.end()
    return pm


def _icon_terminal(size, color):
    pm, p = _canvas(size)
    s = size
    pen = _pen(color, s)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    p.drawRoundedRect(QRectF(s * 0.10, s * 0.18, s * 0.80, s * 0.64),
                      s * 0.10, s * 0.10)
    pen2 = _pen_bold(color, s)
    p.setPen(pen2)
    p.drawLine(QPointF(s * 0.26, s * 0.40), QPointF(s * 0.38, s * 0.52))
    p.drawLine(QPointF(s * 0.38, s * 0.52), QPointF(s * 0.26, s * 0.64))
    p.drawLine(QPointF(s * 0.48, s * 0.66), QPointF(s * 0.68, s * 0.66))
    p.end()
    return pm


def _icon_taskmgr(size, color):
    pm, p = _canvas(size)
    s = size
    pen = _pen_bold(color, s)
    p.setPen(pen)
    p.drawLine(QPointF(s * 0.24, s * 0.72), QPointF(s * 0.24, s * 0.52))
    p.drawLine(QPointF(s * 0.44, s * 0.72), QPointF(s * 0.44, s * 0.36))
    p.drawLine(QPointF(s * 0.64, s * 0.72), QPointF(s * 0.64, s * 0.22))
    pen2 = _pen_thin(color, s)
    p.setPen(pen2)
    p.drawLine(QPointF(s * 0.14, s * 0.82), QPointF(s * 0.86, s * 0.82))
    p.end()
    return pm


def _icon_shield(size, color):
    pm, p = _canvas(size)
    s = size
    pen = _pen(color, s)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    path = QPainterPath()
    path.moveTo(s * 0.5, s * 0.14)
    path.lineTo(s * 0.84, s * 0.28)
    path.lineTo(s * 0.84, s * 0.52)
    path.quadTo(s * 0.84, s * 0.76, s * 0.5, s * 0.88)
    path.quadTo(s * 0.16, s * 0.76, s * 0.16, s * 0.52)
    path.lineTo(s * 0.16, s * 0.28)
    path.closeSubpath()
    p.drawPath(path)
    p.end()
    return pm


def _icon_key(size, color):
    pm, p = _canvas(size)
    s = size
    pen = _pen(color, s)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    cx, cy = s * 0.36, s * 0.5
    r = s * 0.14
    p.drawEllipse(QPointF(cx, cy), r, r)
    p.drawEllipse(QPointF(cx, cy), r * 0.4, r * 0.4)
    p.drawLine(QPointF(cx + r * 0.9, cy), QPointF(s * 0.84, cy))
    p.drawLine(QPointF(s * 0.72, cy), QPointF(s * 0.72, cy + s * 0.12))
    p.drawLine(QPointF(s * 0.82, cy), QPointF(s * 0.82, cy + s * 0.08))
    p.end()
    return pm


# ============================================================
#  ФАЙЛЫ
# ============================================================

def _icon_files(size, color):
    pm, p = _canvas(size)
    s = size
    pen = _pen(color, s)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    path = QPainterPath()
    path.moveTo(s * 0.12, s * 0.30)
    path.lineTo(s * 0.42, s * 0.30)
    path.lineTo(s * 0.50, s * 0.40)
    path.lineTo(s * 0.88, s * 0.40)
    path.lineTo(s * 0.88, s * 0.78)
    path.lineTo(s * 0.12, s * 0.78)
    path.closeSubpath()
    p.drawPath(path)
    p.end()
    return pm


def _icon_file(size, color):
    pm, p = _canvas(size)
    s = size
    pen = _pen(color, s)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    path = QPainterPath()
    path.moveTo(s * 0.22, s * 0.14)
    path.lineTo(s * 0.62, s * 0.14)
    path.lineTo(s * 0.78, s * 0.30)
    path.lineTo(s * 0.78, s * 0.86)
    path.lineTo(s * 0.22, s * 0.86)
    path.closeSubpath()
    p.drawPath(path)
    p.drawLine(QPointF(s * 0.62, s * 0.14), QPointF(s * 0.62, s * 0.30))
    p.drawLine(QPointF(s * 0.62, s * 0.30), QPointF(s * 0.78, s * 0.30))
    p.end()
    return pm


def _icon_editor(size, color):
    pm, p = _canvas(size)
    s = size
    pen = _pen(color, s)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    path = QPainterPath()
    path.moveTo(s * 0.22, s * 0.14)
    path.lineTo(s * 0.62, s * 0.14)
    path.lineTo(s * 0.78, s * 0.30)
    path.lineTo(s * 0.78, s * 0.86)
    path.lineTo(s * 0.22, s * 0.86)
    path.closeSubpath()
    p.drawPath(path)
    p.drawLine(QPointF(s * 0.62, s * 0.14), QPointF(s * 0.62, s * 0.30))
    p.drawLine(QPointF(s * 0.62, s * 0.30), QPointF(s * 0.78, s * 0.30))
    pen2 = _pen_thin(color, s)
    p.setPen(pen2)
    for y in (0.48, 0.60, 0.72):
        p.drawLine(QPointF(s * 0.34, s * y), QPointF(s * 0.66, s * y))
    p.end()
    return pm


def _icon_save(size, color):
    pm, p = _canvas(size)
    s = size
    pen = _pen(color, s)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    p.drawRoundedRect(QRectF(s * 0.14, s * 0.14, s * 0.72, s * 0.72),
                      s * 0.08, s * 0.08)
    p.drawRect(QRectF(s * 0.30, s * 0.14, s * 0.40, s * 0.26))
    p.drawRect(QRectF(s * 0.26, s * 0.58, s * 0.48, s * 0.28))
    p.end()
    return pm


def _icon_download(size, color):
    pm, p = _canvas(size)
    s = size
    pen = _pen(color, s)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    p.drawLine(QPointF(s * 0.5, s * 0.14), QPointF(s * 0.5, s * 0.60))
    p.drawLine(QPointF(s * 0.30, s * 0.42), QPointF(s * 0.5, s * 0.62))
    p.drawLine(QPointF(s * 0.70, s * 0.42), QPointF(s * 0.5, s * 0.62))
    p.drawLine(QPointF(s * 0.18, s * 0.82), QPointF(s * 0.82, s * 0.82))
    p.end()
    return pm


def _icon_upload(size, color):
    pm, p = _canvas(size)
    s = size
    pen = _pen(color, s)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    p.drawLine(QPointF(s * 0.5, s * 0.86), QPointF(s * 0.5, s * 0.40))
    p.drawLine(QPointF(s * 0.30, s * 0.58), QPointF(s * 0.5, s * 0.38))
    p.drawLine(QPointF(s * 0.70, s * 0.58), QPointF(s * 0.5, s * 0.38))
    p.drawLine(QPointF(s * 0.18, s * 0.86), QPointF(s * 0.82, s * 0.86))
    p.end()
    return pm


# ============================================================
#  МЕДИА
# ============================================================

def _icon_music(size, color):
    pm, p = _canvas(size)
    s = size
    pen = _pen(color, s)
    p.setPen(pen)
    p.drawLine(QPointF(s * 0.42, s * 0.22), QPointF(s * 0.42, s * 0.70))
    p.drawLine(QPointF(s * 0.72, s * 0.30), QPointF(s * 0.72, s * 0.66))
    pen2 = _pen_bold(color, s)
    p.setPen(pen2)
    p.drawLine(QPointF(s * 0.42, s * 0.22), QPointF(s * 0.72, s * 0.30))
    p.setBrush(QBrush(QColor(color)))
    p.setPen(Qt.NoPen)
    p.drawEllipse(QPointF(s * 0.34, s * 0.70), s * 0.11, s * 0.085)
    p.drawEllipse(QPointF(s * 0.64, s * 0.66), s * 0.11, s * 0.085)
    p.end()
    return pm


def _icon_gallery(size, color):
    pm, p = _canvas(size)
    s = size
    pen = _pen(color, s)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    p.drawRoundedRect(QRectF(s * 0.12, s * 0.18, s * 0.76, s * 0.64),
                      s * 0.08, s * 0.08)
    p.setBrush(QBrush(QColor(color)))
    p.setPen(Qt.NoPen)
    p.drawEllipse(QPointF(s * 0.34, s * 0.38), s * 0.07, s * 0.07)
    pen2 = _pen_thin(color, s)
    p.setPen(pen2)
    p.setBrush(Qt.NoBrush)
    path = QPainterPath()
    path.moveTo(s * 0.16, s * 0.72)
    path.lineTo(s * 0.36, s * 0.50)
    path.lineTo(s * 0.52, s * 0.66)
    path.lineTo(s * 0.68, s * 0.48)
    path.lineTo(s * 0.84, s * 0.72)
    p.drawPath(path)
    p.end()
    return pm


def _icon_video(size, color):
    pm, p = _canvas(size)
    s = size
    pen = _pen(color, s)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    p.drawRoundedRect(QRectF(s * 0.14, s * 0.30, s * 0.54, s * 0.40),
                      s * 0.06, s * 0.06)
    path = QPainterPath()
    path.moveTo(s * 0.68, s * 0.42)
    path.lineTo(s * 0.86, s * 0.34)
    path.lineTo(s * 0.86, s * 0.66)
    path.lineTo(s * 0.68, s * 0.58)
    path.closeSubpath()
    p.drawPath(path)
    p.end()
    return pm


def _icon_camera(size, color):
    pm, p = _canvas(size)
    s = size
    pen = _pen(color, s)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    p.drawRoundedRect(QRectF(s * 0.12, s * 0.30, s * 0.76, s * 0.50),
                      s * 0.08, s * 0.08)
    p.drawLine(QPointF(s * 0.36, s * 0.30), QPointF(s * 0.36, s * 0.22))
    p.drawLine(QPointF(s * 0.36, s * 0.22), QPointF(s * 0.60, s * 0.22))
    p.drawLine(QPointF(s * 0.60, s * 0.22), QPointF(s * 0.60, s * 0.30))
    p.drawEllipse(QPointF(s * 0.5, s * 0.55), s * 0.14, s * 0.14)
    p.end()
    return pm


def _icon_mic(size, color):
    pm, p = _canvas(size)
    s = size
    pen = _pen(color, s)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    p.drawRoundedRect(QRectF(s * 0.36, s * 0.14, s * 0.28, s * 0.44),
                      s * 0.14, s * 0.14)
    path = QPainterPath()
    path.moveTo(s * 0.24, s * 0.52)
    path.quadTo(s * 0.24, s * 0.76, s * 0.5, s * 0.76)
    path.quadTo(s * 0.76, s * 0.76, s * 0.76, s * 0.52)
    p.drawPath(path)
    p.drawLine(QPointF(s * 0.5, s * 0.76), QPointF(s * 0.5, s * 0.88))
    p.drawLine(QPointF(s * 0.34, s * 0.88), QPointF(s * 0.66, s * 0.88))
    p.end()
    return pm


def _icon_radio(size, color):
    pm, p = _canvas(size)
    s = size
    pen = _pen(color, s)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    p.drawRoundedRect(QRectF(s * 0.10, s * 0.32, s * 0.80, s * 0.50),
                      s * 0.08, s * 0.08)
    p.drawLine(QPointF(s * 0.68, s * 0.32), QPointF(s * 0.82, s * 0.12))
    p.drawEllipse(QPointF(s * 0.30, s * 0.57), s * 0.13, s * 0.13)
    p.drawEllipse(QPointF(s * 0.62, s * 0.50), s * 0.03, s * 0.03)
    p.drawEllipse(QPointF(s * 0.74, s * 0.50), s * 0.03, s * 0.03)
    p.drawLine(QPointF(s * 0.58, s * 0.68), QPointF(s * 0.78, s * 0.68))
    p.end()
    return pm


# ============================================================
#  ИНТЕРНЕТ
# ============================================================

def _icon_globe(size, color):
    pm, p = _canvas(size)
    s = size
    pen = _pen(color, s)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    p.drawEllipse(QRectF(s * 0.14, s * 0.14, s * 0.72, s * 0.72))
    p.drawEllipse(QRectF(s * 0.34, s * 0.14, s * 0.32, s * 0.72))
    p.drawLine(QPointF(s * 0.14, s * 0.50), QPointF(s * 0.86, s * 0.50))
    p.end()
    return pm


def _icon_browser(size, color):
    pm, p = _canvas(size)
    s = size
    pen = _pen(color, s)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    p.drawEllipse(QRectF(s * 0.14, s * 0.14, s * 0.72, s * 0.72))
    p.drawEllipse(QRectF(s * 0.34, s * 0.14, s * 0.32, s * 0.72))
    p.drawLine(QPointF(s * 0.14, s * 0.50), QPointF(s * 0.86, s * 0.50))
    pen2 = _pen_thin(color, s)
    p.setPen(pen2)
    p.save()
    p.translate(s / 2, s / 2)
    p.rotate(-25)
    p.drawEllipse(QRectF(-s * 0.42, -s * 0.14, s * 0.84, s * 0.28))
    p.restore()
    p.end()
    return pm


def _icon_wifi(size, color):
    pm, p = _canvas(size)
    s = size
    pen = _pen_bold(color, s)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    cx, cy = s * 0.5, s * 0.72
    for r_factor in (0.20, 0.36, 0.52):
        r = s * r_factor
        rect = QRectF(cx - r, cy - r, r * 2, r * 2)
        p.drawArc(rect, 45 * 16, 90 * 16)
    p.setBrush(QBrush(QColor(color)))
    p.setPen(Qt.NoPen)
    p.drawEllipse(QPointF(cx, cy), s * 0.05, s * 0.05)
    p.end()
    return pm


def _icon_cloud(size, color):
    pm, p = _canvas(size)
    s = size
    pen = _pen(color, s)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    path = QPainterPath()
    path.moveTo(s * 0.26, s * 0.68)
    path.quadTo(s * 0.14, s * 0.68, s * 0.14, s * 0.54)
    path.quadTo(s * 0.14, s * 0.40, s * 0.30, s * 0.40)
    path.quadTo(s * 0.34, s * 0.22, s * 0.52, s * 0.22)
    path.quadTo(s * 0.70, s * 0.22, s * 0.74, s * 0.40)
    path.quadTo(s * 0.88, s * 0.42, s * 0.88, s * 0.56)
    path.quadTo(s * 0.88, s * 0.68, s * 0.74, s * 0.68)
    path.closeSubpath()
    p.drawPath(path)
    p.end()
    return pm


def _icon_mail(size, color):
    pm, p = _canvas(size)
    s = size
    pen = _pen(color, s)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    p.drawRoundedRect(QRectF(s * 0.14, s * 0.28, s * 0.72, s * 0.46),
                      s * 0.06, s * 0.06)
    p.drawLine(QPointF(s * 0.14, s * 0.32), QPointF(s * 0.5, s * 0.56))
    p.drawLine(QPointF(s * 0.5, s * 0.56), QPointF(s * 0.86, s * 0.32))
    p.end()
    return pm


def _icon_chat(size, color):
    pm, p = _canvas(size)
    s = size
    pen = _pen(color, s)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    path = QPainterPath()
    path.addRoundedRect(QRectF(s * 0.12, s * 0.18, s * 0.76, s * 0.52),
                        s * 0.12, s * 0.12)
    p.drawPath(path)
    p.drawLine(QPointF(s * 0.26, s * 0.70), QPointF(s * 0.22, s * 0.86))
    p.drawLine(QPointF(s * 0.22, s * 0.86), QPointF(s * 0.38, s * 0.70))
    pen2 = _pen_bold(color, s)
    p.setPen(pen2)
    for x in (0.36, 0.5, 0.64):
        p.drawPoint(QPointF(s * x, s * 0.44))
    p.end()
    return pm


# ============================================================
#  УТИЛИТЫ
# ============================================================

def _icon_calculator(size, color):
    pm, p = _canvas(size)
    s = size
    pen = _pen(color, s)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    p.drawRoundedRect(QRectF(s * 0.20, s * 0.14, s * 0.60, s * 0.72),
                      s * 0.08, s * 0.08)
    p.drawLine(QPointF(s * 0.28, s * 0.28), QPointF(s * 0.72, s * 0.28))
    pen2 = _pen_bold(color, s)
    p.setPen(pen2)
    for row in range(3):
        for col in range(3):
            x = s * 0.32 + col * s * 0.14
            y = s * 0.46 + row * s * 0.14
            p.drawPoint(QPointF(x, y))
    p.end()
    return pm


def _icon_clock(size, color):
    pm, p = _canvas(size)
    s = size
    pen = _pen(color, s)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    p.drawEllipse(QRectF(s * 0.14, s * 0.14, s * 0.72, s * 0.72))
    p.drawLine(QPointF(s * 0.50, s * 0.50), QPointF(s * 0.50, s * 0.28))
    p.drawLine(QPointF(s * 0.50, s * 0.50), QPointF(s * 0.70, s * 0.54))
    p.setBrush(QBrush(QColor(color)))
    p.setPen(Qt.NoPen)
    for x, y in [(0.5, 0.18), (0.82, 0.5), (0.5, 0.82), (0.18, 0.5)]:
        p.drawEllipse(QPointF(s * x, s * y), s * 0.03, s * 0.03)
    p.end()
    return pm


def _icon_calendar(size, color):
    pm, p = _canvas(size)
    s = size
    pen = _pen(color, s)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    p.drawRoundedRect(QRectF(s * 0.14, s * 0.22, s * 0.72, s * 0.64),
                      s * 0.06, s * 0.06)
    p.drawLine(QPointF(s * 0.14, s * 0.38), QPointF(s * 0.86, s * 0.38))
    p.drawLine(QPointF(s * 0.32, s * 0.14), QPointF(s * 0.32, s * 0.26))
    p.drawLine(QPointF(s * 0.68, s * 0.14), QPointF(s * 0.68, s * 0.26))
    p.setBrush(QBrush(QColor(color)))
    p.setPen(Qt.NoPen)
    for row in range(2):
        for col in range(3):
            x = s * 0.30 + col * s * 0.20
            y = s * 0.52 + row * s * 0.15
            p.drawEllipse(QPointF(x, y), s * 0.025, s * 0.025)
    p.end()
    return pm


def _icon_grid(size, color):
    pm, p = _canvas(size)
    s = size
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(QColor(color)))
    for r in range(3):
        for c in range(3):
            x = s * 0.24 + c * s * 0.20
            y = s * 0.24 + r * s * 0.20
            p.drawEllipse(QPointF(x, y), s * 0.06, s * 0.06)
    p.end()
    return pm


def _icon_search(size, color):
    pm, p = _canvas(size)
    s = size
    pen = _pen_bold(color, s)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    p.drawEllipse(QRectF(s * 0.18, s * 0.18, s * 0.48, s * 0.48))
    p.drawLine(QPointF(s * 0.60, s * 0.60), QPointF(s * 0.84, s * 0.84))
    p.end()
    return pm


def _icon_star(size, color):
    pm, p = _canvas(size)
    s = size
    pen = _pen(color, s)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    path = QPainterPath()
    cx, cy = s * 0.5, s * 0.52
    outer = s * 0.36
    inner = s * 0.15
    for i in range(10):
        a = math.radians(-90 + i * 36)
        r = outer if i % 2 == 0 else inner
        x = cx + math.cos(a) * r
        y = cy + math.sin(a) * r
        if i == 0:
            path.moveTo(x, y)
        else:
            path.lineTo(x, y)
    path.closeSubpath()
    p.drawPath(path)
    p.end()
    return pm


def _icon_star_filled(size, color):
    pm, p = _canvas(size)
    s = size
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(QColor(color)))
    path = QPainterPath()
    cx, cy = s * 0.5, s * 0.52
    outer = s * 0.36
    inner = s * 0.15
    for i in range(10):
        a = math.radians(-90 + i * 36)
        r = outer if i % 2 == 0 else inner
        x = cx + math.cos(a) * r
        y = cy + math.sin(a) * r
        if i == 0:
            path.moveTo(x, y)
        else:
            path.lineTo(x, y)
    path.closeSubpath()
    p.drawPath(path)
    p.end()
    return pm


def _icon_plus(size, color):
    pm, p = _canvas(size)
    s = size
    pen = _pen_bold(color, s)
    p.setPen(pen)
    p.drawLine(QPointF(s * 0.5, s * 0.22), QPointF(s * 0.5, s * 0.78))
    p.drawLine(QPointF(s * 0.22, s * 0.5), QPointF(s * 0.78, s * 0.5))
    p.end()
    return pm


def _icon_minus(size, color):
    pm, p = _canvas(size)
    s = size
    pen = _pen_bold(color, s)
    p.setPen(pen)
    p.drawLine(QPointF(s * 0.22, s * 0.5), QPointF(s * 0.78, s * 0.5))
    p.end()
    return pm


def _icon_close(size, color):
    pm, p = _canvas(size)
    s = size
    pen = _pen_bold(color, s)
    p.setPen(pen)
    p.drawLine(QPointF(s * 0.26, s * 0.26), QPointF(s * 0.74, s * 0.74))
    p.drawLine(QPointF(s * 0.74, s * 0.26), QPointF(s * 0.26, s * 0.74))
    p.end()
    return pm


def _icon_check(size, color):
    pm, p = _canvas(size)
    s = size
    pen = _pen_bold(color, s)
    p.setPen(pen)
    p.drawLine(QPointF(s * 0.20, s * 0.52), QPointF(s * 0.42, s * 0.74))
    p.drawLine(QPointF(s * 0.42, s * 0.74), QPointF(s * 0.82, s * 0.28))
    p.end()
    return pm


def _icon_back(size, color):
    pm, p = _canvas(size)
    s = size
    pen = _pen_bold(color, s)
    p.setPen(pen)
    p.drawLine(QPointF(s * 0.62, s * 0.24), QPointF(s * 0.36, s * 0.50))
    p.drawLine(QPointF(s * 0.36, s * 0.50), QPointF(s * 0.62, s * 0.76))
    p.end()
    return pm


def _icon_forward(size, color):
    pm, p = _canvas(size)
    s = size
    pen = _pen_bold(color, s)
    p.setPen(pen)
    p.drawLine(QPointF(s * 0.38, s * 0.24), QPointF(s * 0.64, s * 0.50))
    p.drawLine(QPointF(s * 0.64, s * 0.50), QPointF(s * 0.38, s * 0.76))
    p.end()
    return pm


def _icon_reload(size, color):
    pm, p = _canvas(size)
    s = size
    pen = _pen(color, s)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    rect = QRectF(s * 0.18, s * 0.18, s * 0.64, s * 0.64)
    p.drawArc(rect, 45 * 16, 270 * 16)
    p.setBrush(QBrush(QColor(color)))
    p.setPen(Qt.NoPen)
    arrow = QPainterPath()
    end_x = s * 0.82
    end_y = s * 0.42
    arrow.moveTo(end_x, end_y)
    arrow.lineTo(end_x - s * 0.15, end_y - s * 0.03)
    arrow.lineTo(end_x - s * 0.05, end_y + s * 0.14)
    arrow.closeSubpath()
    p.drawPath(arrow)
    p.end()
    return pm


def _icon_home(size, color):
    pm, p = _canvas(size)
    s = size
    pen = _pen(color, s)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    path = QPainterPath()
    path.moveTo(s * 0.16, s * 0.48)
    path.lineTo(s * 0.50, s * 0.18)
    path.lineTo(s * 0.84, s * 0.48)
    p.drawPath(path)
    p.drawRect(QRectF(s * 0.26, s * 0.48, s * 0.48, s * 0.36))
    p.drawRect(QRectF(s * 0.42, s * 0.64, s * 0.16, s * 0.20))
    p.end()
    return pm


def _icon_trash(size, color):
    pm, p = _canvas(size)
    s = size
    pen = _pen(color, s)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    p.drawLine(QPointF(s * 0.22, s * 0.28), QPointF(s * 0.78, s * 0.28))
    p.drawRect(QRectF(s * 0.28, s * 0.28, s * 0.44, s * 0.58))
    p.drawLine(QPointF(s * 0.40, s * 0.18), QPointF(s * 0.60, s * 0.18))
    pen2 = _pen_thin(color, s)
    p.setPen(pen2)
    p.drawLine(QPointF(s * 0.42, s * 0.40), QPointF(s * 0.42, s * 0.76))
    p.drawLine(QPointF(s * 0.58, s * 0.40), QPointF(s * 0.58, s * 0.76))
    p.end()
    return pm


def _icon_bell(size, color):
    pm, p = _canvas(size)
    s = size
    pen = _pen(color, s)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    path = QPainterPath()
    path.moveTo(s * 0.30, s * 0.62)
    path.lineTo(s * 0.30, s * 0.42)
    path.quadTo(s * 0.30, s * 0.20, s * 0.50, s * 0.20)
    path.quadTo(s * 0.70, s * 0.20, s * 0.70, s * 0.42)
    path.lineTo(s * 0.70, s * 0.62)
    p.drawPath(path)
    p.drawLine(QPointF(s * 0.26, s * 0.62), QPointF(s * 0.74, s * 0.62))
    p.drawLine(QPointF(s * 0.44, s * 0.70), QPointF(s * 0.56, s * 0.70))
    p.drawLine(QPointF(s * 0.44, s * 0.70), QPointF(s * 0.50, s * 0.78))
    p.drawLine(QPointF(s * 0.56, s * 0.70), QPointF(s * 0.50, s * 0.78))
    p.end()
    return pm


def _icon_lock(size, color):
    pm, p = _canvas(size)
    s = size
    pen = _pen(color, s)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    p.drawRoundedRect(QRectF(s * 0.22, s * 0.44, s * 0.56, s * 0.42),
                      s * 0.08, s * 0.08)
    path = QPainterPath()
    path.moveTo(s * 0.34, s * 0.44)
    path.lineTo(s * 0.34, s * 0.32)
    path.quadTo(s * 0.34, s * 0.16, s * 0.50, s * 0.16)
    path.quadTo(s * 0.66, s * 0.16, s * 0.66, s * 0.32)
    path.lineTo(s * 0.66, s * 0.44)
    p.drawPath(path)
    p.setBrush(QBrush(QColor(color)))
    p.setPen(Qt.NoPen)
    p.drawEllipse(QPointF(s * 0.5, s * 0.62), s * 0.05, s * 0.05)
    p.end()
    return pm


def _icon_unlock(size, color):
    pm, p = _canvas(size)
    s = size
    pen = _pen(color, s)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    p.drawRoundedRect(QRectF(s * 0.22, s * 0.44, s * 0.56, s * 0.42),
                      s * 0.08, s * 0.08)
    path = QPainterPath()
    path.moveTo(s * 0.34, s * 0.44)
    path.lineTo(s * 0.34, s * 0.32)
    path.quadTo(s * 0.34, s * 0.16, s * 0.50, s * 0.16)
    path.quadTo(s * 0.66, s * 0.16, s * 0.66, s * 0.28)
    p.drawPath(path)
    p.setBrush(QBrush(QColor(color)))
    p.setPen(Qt.NoPen)
    p.drawEllipse(QPointF(s * 0.5, s * 0.62), s * 0.05, s * 0.05)
    p.end()
    return pm


# ============================================================
#  РЕЕСТР
# ============================================================

_REGISTRY = {
    # Система
    "settings":   _icon_settings,
    "power":      _icon_power,
    "terminal":   _icon_terminal,
    "taskmgr":    _icon_taskmgr,
    "shield":     _icon_shield,
    "key":        _icon_key,

    # Файлы
    "files":      _icon_files,
    "folder":     _icon_files,
    "file":       _icon_file,
    "editor":     _icon_editor,
    "save":       _icon_save,
    "download":   _icon_download,
    "upload":     _icon_upload,

    # Медиа
    "music":      _icon_music,
    "gallery":    _icon_gallery,
    "video":      _icon_video,
    "camera":     _icon_camera,
    "mic":        _icon_mic,
    "radio":      _icon_radio,

    # Интернет
    "globe":      _icon_globe,
    "browser":    _icon_browser,
    "wifi":       _icon_wifi,
    "cloud":      _icon_cloud,
    "mail":       _icon_mail,
    "chat":       _icon_chat,

    # Утилиты
    "calculator": _icon_calculator,
    "clock":      _icon_clock,
    "calendar":   _icon_calendar,
    "grid":       _icon_grid,
    "search":     _icon_search,
    "star":       _icon_star,
    "star_filled":_icon_star_filled,
    "plus":       _icon_plus,
    "minus":      _icon_minus,
    "close":      _icon_close,
    "check":      _icon_check,
    "back":       _icon_back,
    "forward":    _icon_forward,
    "reload":     _icon_reload,
    "home":       _icon_home,
    "trash":      _icon_trash,
    "bell":       _icon_bell,
    "lock":       _icon_lock,
    "unlock":     _icon_unlock,
}


# ============================================================
#  Умный маппинг по ключевым словам
# ============================================================

_KEYWORD_MAP = [
    # файлы / папки
    ("folder",      "files"),
    ("dir",         "files"),
    ("explorer",    "files"),
    ("проводник",   "files"),
    ("file",        "file"),

    # заметки / текст
    ("note",        "editor"),
    ("text",        "editor"),
    ("edit",        "editor"),
    ("write",       "editor"),
    ("word",        "editor"),
    ("document",    "editor"),
    ("блокнот",     "editor"),
    ("заметк",      "editor"),
    ("diary",       "editor"),
    ("book",        "editor"),
    ("read",        "editor"),
    ("книг",        "editor"),

    # терминал / IDE
    ("term",        "terminal"),
    ("console",     "terminal"),
    ("shell",       "terminal"),
    ("cmd",         "terminal"),
    ("bash",        "terminal"),
    ("ide",         "terminal"),
    ("develop",     "terminal"),
    ("программ",    "terminal"),

    # настройки
    ("setting",     "settings"),
    ("config",      "settings"),
    ("pref",        "settings"),
    ("настрой",     "settings"),

    # диспетчер / графики
    ("task",        "taskmgr"),
    ("monitor",     "taskmgr"),
    ("process",     "taskmgr"),
    ("sysmon",      "taskmgr"),
    ("plot",        "taskmgr"),
    ("graph",       "taskmgr"),
    ("chart",       "taskmgr"),
    ("график",      "taskmgr"),

    # калькулятор / счёт
    ("calc",        "calculator"),
    ("math",        "calculator"),
    ("count",       "calculator"),
    ("currency",    "calculator"),
    ("money",       "calculator"),
    ("rate",        "calculator"),
    ("курс",        "calculator"),

    # время
    ("clock",       "clock"),
    ("time",        "clock"),
    ("watch",       "clock"),

    # календарь
    ("calendar",    "calendar"),
    ("date",        "calendar"),
    ("schedule",    "calendar"),

    # картинки / графика
    ("gallery",     "gallery"),
    ("image",       "gallery"),
    ("pic",         "gallery"),
    ("paint",       "gallery"),
    ("draw",        "gallery"),
    ("photo",       "camera"),

    # музыка / звук
    ("music",       "music"),
    ("sound",       "music"),
    ("audio",       "music"),
    ("player",      "music"),
    ("song",        "music"),

    # видео / камера / гиф
    ("video",       "video"),
    ("movie",       "video"),
    ("gif",         "video"),
    ("anim",        "video"),
    ("camera",      "camera"),

    # интернет
    ("browser",     "browser"),
    ("web",         "globe"),
    ("internet",    "globe"),
    ("net",         "wifi"),
    ("wifi",        "wifi"),
    ("network",     "wifi"),

    # радио
    ("radio",       "radio"),
    ("fm",          "radio"),
    ("station",     "radio"),

    # почта / чат
    ("mail",        "mail"),
    ("email",       "mail"),
    ("chat",        "chat"),
    ("message",     "chat"),
    ("messenger",   "chat"),
    ("сообщ",       "chat"),

    # погода / облака
    ("weather",     "cloud"),
    ("forecast",    "cloud"),
    ("погод",       "cloud"),

    # QR / код
    ("qr",          "grid"),

    # скорость / тест
    ("speed",       "forward"),
    ("test",        "forward"),
    ("ping",        "forward"),

    # магазин
    ("store",       "download"),
    ("shop",        "download"),
    ("market",      "download"),
    ("install",     "download"),
    ("магазин",     "download"),

    # пароли / защита
    ("pass",        "lock"),
    ("secure",      "lock"),
    ("vault",       "lock"),
    ("парол",       "lock"),

    # игры
    ("game",        "grid"),
    ("2048",        "grid"),
    ("mine",        "grid"),
    ("sweep",       "grid"),
    ("sudoku",      "grid"),
    ("memory",      "grid"),
    ("card",        "grid"),
    ("solit",       "grid"),
    ("flash",       "grid"),
    ("quiz",        "grid"),
    ("обуч",        "grid"),
    ("periodic",    "grid"),
    ("table",       "grid"),
    ("element",     "grid"),

    # прочее
    ("pet",         "star"),
    ("todo",        "check"),
    ("habit",       "check"),
]


def _smart_icon(name: str):
    """Точное имя → подстрока в реестре → ключевые слова."""
    if not name:
        return None
    low = name.lower()

    # 1. Точное совпадение
    if low in _REGISTRY:
        return _REGISTRY[low]

    # 2. Подстрока в реестре (например, "clock_widget" → "clock")
    for key in _REGISTRY:
        if key in low:
            return _REGISTRY[key]

    # 3. По ключевым словам
    for keyword, icon_key in _KEYWORD_MAP:
        if keyword in low and icon_key in _REGISTRY:
            return _REGISTRY[icon_key]

    return None


def get_icon(name: str, size: int = 32, color: str = "#FFFFFF") -> QPixmap:
    """Возвращает иконку по имени с умным подбором."""
    fn = _smart_icon(name)
    if fn is None:
        return _icon_globe(size, color)
    return fn(size, color)


def available_icons() -> list:
    """Список всех доступных ключей."""
    return sorted(_REGISTRY.keys())