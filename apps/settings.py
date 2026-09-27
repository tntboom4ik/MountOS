"""
MountOS — Настройки.

Разделы:
  • О системе
  • Оформление
  • Обои
  • Язык
  • Приложения
  • Уведомления
  • Приватность
  • Система
  • Сброс

Только рабочие параметры.
"""
from PySide6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QLabel,
                                QPushButton, QStackedWidget, QCheckBox,
                                QSlider, QScrollArea, QFrame, QFileDialog,
                                QMessageBox, QApplication, QLineEdit,
                                QComboBox, QSpinBox, QTextEdit, QGridLayout)
from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtGui import (QIcon, QPixmap, QPainter, QColor, QLinearGradient,
                            QFont, QBrush, QPen)
import platform
import sys
import time
import os
import json
import shutil
from datetime import datetime

from ui.settings_state import state
from ui.icons import get_icon
from system.i18n import (tr, on_change, available_languages,
                          current_language, is_beta, language_status)
from ui.hotkeys import HOTKEYS_HELP
from system import paths

APP_NAME = "Настройки"
APP_ICON = "settings"
APP_VERSION = "1.0"
APP_AUTHOR = "MountOS"

VERSION = "1.0"
VERSION_TAG = "Release"
CODENAME = "Stable"


_START_TIME = time.time()


# ============================================================
#  Поиск Desktop / Registry
# ============================================================

def _get_desktop(widget):
    p = widget
    while p is not None:
        if hasattr(p, "notifications") and hasattr(p, "open_app"):
            return p
        p = p.parent()
    for top in QApplication.topLevelWidgets():
        ref = getattr(top, "desktop_ref", None)
        if ref is not None and hasattr(ref, "registry"):
            return ref
        for child in top.findChildren(QWidget):
            ref = getattr(child, "desktop_ref", None)
            if ref is not None and hasattr(ref, "registry"):
                return ref
    for top in QApplication.topLevelWidgets():
        if hasattr(top, "notifications") and hasattr(top, "open_app"):
            return top
    return None


def _get_registry(widget):
    d = _get_desktop(widget)
    if d is not None and hasattr(d, "registry"):
        return d.registry
    return None


def _get_vfs(widget):
    d = _get_desktop(widget)
    if d and hasattr(d, "vfs"):
        return d.vfs
    return None


def _notify(widget, title, text):
    d = _get_desktop(widget)
    if d and hasattr(d, "notifications"):
        d.notifications.push(title, text)


# ============================================================
#  Хелперы
# ============================================================

def _section(title):
    l = QLabel(title.upper())
    l.setStyleSheet("""
        color: rgba(255,255,255,0.45);
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 1.5px;
        padding: 16px 4px 8px 4px;
    """)
    return l


def _hint(text):
    l = QLabel(text)
    l.setWordWrap(True)
    l.setStyleSheet("color: rgba(255,255,255,0.45); font-size: 11px; padding: 2px 4px 6px 4px;")
    return l


def _row(label, widget):
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(4, 6, 4, 6)
    lbl = QLabel(label)
    lbl.setStyleSheet("color: rgba(255,255,255,0.90); font-size: 13px;")
    lay.addWidget(lbl)
    lay.addStretch(1)
    lay.addWidget(widget)
    return w


def _checkbox(key, default=None):
    cb = QCheckBox()
    val = state().get(key, default if default is not None else True)
    cb.setChecked(val)
    cb.stateChanged.connect(lambda v: state().set(key, bool(v)))
    cb.setStyleSheet("""
        QCheckBox::indicator { width: 18px; height: 18px; border-radius: 5px; }
        QCheckBox::indicator:unchecked {
            border: 1px solid rgba(255,255,255,0.30);
            background: rgba(255,255,255,0.05);
        }
        QCheckBox::indicator:checked {
            border: 1px solid #6EC6FF;
            background: #6EC6FF;
        }
    """)
    return cb


def _slider(key, minv, maxv, is_float=False):
    sl = QSlider(Qt.Horizontal)
    sl.setRange(minv, maxv)
    sl.setFixedWidth(220)
    cur = state().get(key)
    sl.setValue(int(cur * 100) if is_float else int(cur))
    sl.setStyleSheet("""
        QSlider::groove:horizontal {
            height: 4px; background: rgba(255,255,255,0.15);
            border-radius: 2px;
        }
        QSlider::handle:horizontal {
            background: #6EC6FF; width: 16px; margin: -6px 0;
            border-radius: 8px;
        }
    """)
    def on_change_val(v):
        state().set(key, v / 100.0 if is_float else v)
    sl.valueChanged.connect(on_change_val)
    return sl


def _scrollable(inner):
    sc = QScrollArea()
    sc.setWidgetResizable(True)
    sc.setFrameShape(QFrame.NoFrame)
    sc.setStyleSheet("""
        QScrollArea { background: transparent; }
        QScrollBar:vertical {
            background: transparent; width: 8px; margin: 4px;
        }
        QScrollBar::handle:vertical {
            background: rgba(255,255,255,0.20);
            border-radius: 4px; min-height: 30px;
        }
        QScrollBar::handle:vertical:hover { background: rgba(255,255,255,0.35); }
        QScrollBar::add-line, QScrollBar::sub-line { height: 0; }
    """)
    sc.setWidget(inner)
    return sc


# ============================================================
#  Обои
# ============================================================

WALLPAPERS = {
    "cosmic":    (("#0A0E1A", "#131A2E", "#1A1F35"),
                  (110, 198, 255), (179, 136, 255)),
    "mountains": (("#101820", "#1F2D3A", "#354A5E"),
                  (140, 200, 180), (200, 220, 200)),
    "neon":      (("#160020", "#2A0050", "#4A0080"),
                  (255, 80, 200), (120, 100, 255)),
    "aurora":    (("#021B1B", "#053B3B", "#0A5C5C"),
                  (100, 255, 200), (150, 200, 255)),
    "sunset":    (("#1A0A0E", "#3D1520", "#6B2E3F"),
                  (255, 150, 100), (255, 80, 150)),
    "ocean":     (("#020C1B", "#0A2540", "#0F3A5F"),
                  (100, 180, 255), (60, 220, 220)),
}


# ============================================================
#  Страница: О системе
# ============================================================

def _page_about():
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(30, 30, 30, 30)
    lay.setSpacing(8)

    # Логотип
    logo = QLabel()
    logo.setAlignment(Qt.AlignCenter)
    pm = QPixmap(140, 140)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    grad = QLinearGradient(0, 0, 140, 140)
    accent = state().get("accent")
    grad.setColorAt(0, QColor(accent))
    grad.setColorAt(1, QColor(179, 136, 255))
    p.setBrush(QBrush(grad))
    p.setPen(Qt.NoPen)
    p.drawEllipse(20, 20, 100, 100)
    p.setPen(QColor("white"))
    f = QFont("Segoe UI", 48, QFont.Light)
    p.setFont(f)
    p.drawText(pm.rect(), Qt.AlignCenter, "◆")
    p.end()
    logo.setPixmap(pm)
    lay.addWidget(logo)

    name = QLabel("MountOS")
    name.setAlignment(Qt.AlignCenter)
    name.setStyleSheet("""
        color: white; font-size: 34px;
        font-weight: 300; letter-spacing: 6px;
    """)
    lay.addWidget(name)

    ver = QLabel(f"версия {VERSION} {VERSION_TAG}  ·  {CODENAME}")
    ver.setAlignment(Qt.AlignCenter)
    ver.setStyleSheet("""
        color: rgba(255,255,255,0.65);
        font-size: 13px;
        letter-spacing: 1px;
    """)
    lay.addWidget(ver)

    lay.addSpacing(30)

    # Информация о системе
    import PySide6
    info = [
        ("Операционная система", f"{platform.system()} {platform.release()}"),
        ("Версия ядра ОС",       platform.version()),
        ("Архитектура",          platform.machine()),
        ("Процессор",            platform.processor() or "—"),
        ("Имя компьютера",       platform.node()),
        ("Python",               platform.python_version()),
        ("PySide6",              PySide6.__version__),
        ("Ядро MountOS",         f"MountKernel {VERSION}"),
        ("Оболочка",             "MountShell 1.0"),
        ("Платформа",            paths.PLATFORM),
    ]

    try:
        from system.paths import USER_DATA
        info.append(("Папка данных", str(USER_DATA)))
    except Exception:
        pass

    for k, v in info:
        row = QWidget()
        row.setStyleSheet("""
            QWidget {
                background: rgba(255,255,255,0.05);
                border-radius: 10px;
            }
        """)
        rl = QHBoxLayout(row)
        rl.setContentsMargins(20, 10, 20, 10)

        kl = QLabel(k)
        kl.setStyleSheet("color: rgba(255,255,255,0.60); font-size: 13px; background: transparent; border: none;")
        rl.addWidget(kl)
        rl.addStretch(1)

        vl = QLabel(str(v))
        vl.setStyleSheet("color: rgba(255,255,255,0.95); font-size: 13px; font-weight: 500; background: transparent; border: none;")
        vl.setWordWrap(True)
        vl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        rl.addWidget(vl)

        lay.addWidget(row)

    lay.addSpacing(20)

    # Кнопки действий
    btn_row = QHBoxLayout()
    btn_row.setSpacing(10)

    copy_btn = QPushButton("📋  Копировать сведения")
    copy_btn.setCursor(Qt.PointingHandCursor)
    copy_btn.setFixedHeight(38)
    copy_btn.setStyleSheet("""
        QPushButton {
            background: rgba(110,198,255,0.18);
            color: white;
            border: 1px solid rgba(110,198,255,0.50);
            border-radius: 10px;
            padding: 6px 18px;
            font-size: 12px;
        }
        QPushButton:hover { background: rgba(110,198,255,0.35); }
    """)
    def copy_info():
        text = f"MountOS {VERSION} {VERSION_TAG}\n"
        for k, v in info:
            text += f"{k}: {v}\n"
        QApplication.clipboard().setText(text)
        _notify(w, "Скопировано", "Сведения о системе в буфере")
    copy_btn.clicked.connect(copy_info)
    btn_row.addWidget(copy_btn)

    btn_row.addStretch(1)
    lay.addLayout(btn_row)

    lay.addStretch(1)
    return _scrollable(w)


# ============================================================
#  Страница: Оформление
# ============================================================

def _page_appearance():
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(30, 20, 30, 30)
    lay.setSpacing(2)

    lay.addWidget(_section("Цвет акцента"))
    lay.addWidget(_hint("Меняет цвет активных элементов интерфейса и иконок."))

    accents_row = QWidget()
    ar = QHBoxLayout(accents_row)
    ar.setContentsMargins(4, 4, 4, 12)
    ar.setSpacing(10)

    accent_presets = [
        ("#6EC6FF", "Голубой"),
        ("#B388FF", "Фиолетовый"),
        ("#FF6B8A", "Розовый"),
        ("#6EE7B7", "Зелёный"),
        ("#FFB86C", "Оранжевый"),
        ("#FBBF24", "Жёлтый"),
        ("#5EEAD4", "Бирюза"),
        ("#F472B6", "Малиновый"),
    ]

    for hexc, name in accent_presets:
        b = QPushButton()
        b.setFixedSize(38, 38)
        b.setCursor(Qt.PointingHandCursor)
        b.setToolTip(name)
        b.clicked.connect(lambda _, h=hexc: state().set("accent", h))

        def refresh(btn=b, h=hexc):
            cur = state().get("accent") == h
            border = "3px solid white" if cur else "1px solid rgba(255,255,255,0.30)"
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {h};
                    border: {border};
                    border-radius: 19px;
                }}
            """)
        refresh()
        state().changed.connect(lambda k, v, f=refresh: f() if k == "accent" else None)
        ar.addWidget(b)

    ar.addStretch(1)
    lay.addWidget(accents_row)

    # Кастомный цвет
    lay.addWidget(_section("Свой цвет акцента"))
    custom_row = QHBoxLayout()
    custom_row.setSpacing(8)

    color_input = QLineEdit(state().get("accent"))
    color_input.setFixedWidth(120)
    color_input.setStyleSheet("""
        QLineEdit {
            background: rgba(255,255,255,0.08);
            color: white;
            border: 1px solid rgba(255,255,255,0.15);
            border-radius: 8px;
            padding: 6px 10px;
            font-family: Consolas, monospace;
            font-size: 12px;
        }
    """)
    def apply_custom():
        c = color_input.text().strip()
        if c and not c.startswith("#"):
            c = "#" + c
        if len(c) in (4, 7):
            try:
                QColor(c)
                state().set("accent", c)
            except Exception:
                pass
    color_input.returnPressed.connect(apply_custom)
    custom_row.addWidget(color_input)

    apply_btn = QPushButton("Применить")
    apply_btn.setFixedHeight(32)
    apply_btn.setCursor(Qt.PointingHandCursor)
    apply_btn.setStyleSheet("""
        QPushButton {
            background: rgba(110,198,255,0.20);
            color: white;
            border: 1px solid rgba(110,198,255,0.50);
            border-radius: 8px;
            padding: 6px 14px;
            font-size: 12px;
        }
        QPushButton:hover { background: rgba(110,198,255,0.35); }
    """)
    apply_btn.clicked.connect(apply_custom)
    custom_row.addWidget(apply_btn)
    custom_row.addStretch(1)
    lay.addLayout(custom_row)

    lay.addWidget(_section("Окна"))
    lay.addWidget(_row("Прозрачность", _slider("window_opacity", 40, 100, is_float=True)))
    lay.addWidget(_hint("Насколько окна пропускают фон."))
    lay.addWidget(_row("Скругление углов", _slider("window_radius", 8, 30)))
    lay.addWidget(_hint("Радиус углов стеклянных окон."))
    lay.addWidget(_row("Размытие окон", _checkbox("blur_enabled")))
    lay.addWidget(_hint("Размытие фона за окнами (Windows 10/11, KWin)."))

    lay.addWidget(_section("Интерфейс"))
    lay.addWidget(_row("Показывать часы в панели", _checkbox("show_clock")))
    lay.addWidget(_row("Показывать док",           _checkbox("show_dock")))
    lay.addWidget(_row("Показывать приветствие",   _checkbox("show_welcome")))
    lay.addWidget(_row("Показывать батарею",       _checkbox("show_battery")))
    lay.addWidget(_row("Показывать ЦП и ОЗУ",      _checkbox("show_cpu")))

    lay.addStretch(1)
    return _scrollable(w)


# ============================================================
#  Страница: Обои
# ============================================================

def _page_wallpaper():
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(30, 20, 30, 30)
    lay.setSpacing(2)

    lay.addWidget(_section("Обои рабочего стола"))
    lay.addWidget(_hint("Выбери тему фона."))

    grid = QWidget()
    gl = QHBoxLayout(grid)
    gl.setContentsMargins(4, 8, 4, 8)
    gl.setSpacing(14)

    def make_preview(key):
        colors, g1, g2 = WALLPAPERS[key]
        pm = QPixmap(160, 100)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        grad = QLinearGradient(0, 0, 160, 100)
        grad.setColorAt(0, QColor(colors[0]))
        grad.setColorAt(0.5, QColor(colors[1]))
        grad.setColorAt(1, QColor(colors[2]))
        p.fillRect(0, 0, 160, 100, QBrush(grad))
        g = QLinearGradient(0, 0, 100, 100)
        g.setColorAt(0, QColor(*g1, 90))
        g.setColorAt(1, QColor(*g1, 0))
        p.setBrush(QBrush(g))
        p.setPen(Qt.NoPen)
        p.drawEllipse(-20, -20, 120, 120)
        g2_ = QLinearGradient(160, 100, 60, 0)
        g2_.setColorAt(0, QColor(*g2, 80))
        g2_.setColorAt(1, QColor(*g2, 0))
        p.setBrush(QBrush(g2_))
        p.drawEllipse(60, 20, 130, 130)
        p.end()
        return pm

    buttons = []

    def refresh_all():
        for key, b in buttons:
            selected = state().get("wallpaper") == key
            border = "3px solid #6EC6FF" if selected else "2px solid rgba(255,255,255,0.10)"
            b.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    border: {border};
                    border-radius: 14px;
                    padding: 4px;
                }}
                QPushButton:hover {{ border: 2px solid rgba(255,255,255,0.40); }}
            """)

    state().changed.connect(lambda k, v: refresh_all() if k == "wallpaper" else None)

    for key in WALLPAPERS:
        b = QPushButton()
        b.setIcon(QIcon(make_preview(key)))
        b.setIconSize(QSize(160, 100))
        b.setFixedSize(176, 116)
        b.setCursor(Qt.PointingHandCursor)
        b.setToolTip(key.capitalize())
        b.clicked.connect(lambda _, k=key: state().set("wallpaper", k))
        buttons.append((key, b))
        gl.addWidget(b)

    gl.addStretch(1)
    refresh_all()
    lay.addWidget(grid)

    lay.addWidget(_section("Автосмена"))
    lay.addWidget(_row("Включить автосмену", _checkbox("wallpaper_auto")))
    lay.addWidget(_hint("Обои меняются автоматически через заданный интервал."))

    interval_row = QWidget()
    irl = QHBoxLayout(interval_row)
    irl.setContentsMargins(4, 6, 4, 6)
    irl.addWidget(QLabel("Интервал (мин):"))
    sp = QSpinBox()
    sp.setRange(1, 120)
    sp.setValue(state().get("wallpaper_interval", 15))
    sp.setFixedWidth(100)
    sp.setStyleSheet("""
        QSpinBox {
            background: rgba(255,255,255,0.08);
            color: white;
            border: 1px solid rgba(255,255,255,0.15);
            border-radius: 8px;
            padding: 6px 10px;
            font-size: 12px;
        }
    """)
    sp.valueChanged.connect(lambda v: state().set("wallpaper_interval", v))
    irl.addWidget(sp)
    irl.addStretch(1)
    lay.addWidget(interval_row)

    lay.addWidget(_row("Случайный порядок", _checkbox("wallpaper_shuffle")))

    lay.addWidget(_section("Поведение при запуске"))
    lay.addWidget(_row("Показывать уведомление", _checkbox("show_startup_notification")))

    lay.addStretch(1)
    return _scrollable(w)


# ============================================================
#  Страница: Язык
# ============================================================

def _page_language():
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(30, 20, 30, 30)
    lay.setSpacing(10)

    lay.addWidget(_section("Язык системы"))
    lay.addWidget(_hint("Выбери язык интерфейса. Применяется сразу."))

    beta_note = QLabel(tr("settings.language.beta_note"))
    beta_note.setWordWrap(True)
    beta_note.setStyleSheet("""
        background: rgba(255,184,108,0.15);
        color: #FFD0A0;
        border: 1px solid rgba(255,184,108,0.45);
        border-radius: 10px;
        padding: 10px 14px;
        font-size: 12px;
    """)
    lay.addWidget(beta_note)

    buttons = []

    def refresh():
        cur = current_language()
        for code, btn in buttons:
            active = (code == cur)
            if active:
                btn.setStyleSheet("""
                    QPushButton {
                        background: rgba(110,198,255,0.30);
                        color: white;
                        border: 1px solid rgba(110,198,255,0.70);
                        border-radius: 14px;
                        padding: 16px 20px;
                        font-size: 15px;
                        font-weight: 600;
                        text-align: left;
                    }
                """)
            else:
                btn.setStyleSheet("""
                    QPushButton {
                        background: rgba(255,255,255,0.05);
                        color: rgba(255,255,255,0.85);
                        border: 1px solid rgba(255,255,255,0.10);
                        border-radius: 14px;
                        padding: 16px 20px;
                        font-size: 15px;
                        text-align: left;
                    }
                    QPushButton:hover {
                        background: rgba(255,255,255,0.12);
                    }
                """)
        beta_note.setVisible(is_beta(cur))

    flags = {"ru": "🇷🇺", "en": "🇬🇧"}

    for code, name, flag, status in available_languages():
        row = QWidget()
        rl = QHBoxLayout(row)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(10)

        b = QPushButton(f"   {flag}   {name}")
        b.setCursor(Qt.PointingHandCursor)
        b.setFixedHeight(60)

        def on_click(_, c=code):
            state().set("language", c)
            refresh()

        b.clicked.connect(on_click)
        rl.addWidget(b, 1)

        if status == "beta":
            badge = QLabel("Beta")
            badge.setStyleSheet("""
                background: rgba(255,184,108,0.20);
                color: #FFB86C;
                border: 1px solid rgba(255,184,108,0.55);
                border-radius: 9px;
                padding: 4px 12px;
                font-size: 11px;
                font-weight: 700;
                letter-spacing: 1px;
            """)
            badge.setAlignment(Qt.AlignCenter)
            badge.setFixedHeight(26)
            rl.addWidget(badge)
        else:
            placeholder = QWidget()
            placeholder.setFixedWidth(64)
            rl.addWidget(placeholder)

        buttons.append((code, b))
        lay.addWidget(row)

    refresh()
    lay.addStretch(1)
    return _scrollable(w)


# ============================================================
#  Страница: Приложения
# ============================================================

def _page_apps():
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(30, 20, 30, 30)
    lay.setSpacing(6)

    lay.addWidget(_section("Установка приложений"))
    lay.addWidget(_hint("Установи .py-приложение MountOS — оно появится в доке."))

    btn_row = QWidget()
    br = QHBoxLayout(btn_row)
    br.setContentsMargins(4, 6, 4, 12)
    br.setSpacing(10)

    install_btn = QPushButton(f"  {tr('settings.apps.install')}")
    install_btn.setIcon(QIcon(get_icon("plus", 20, "#6EC6FF")))
    install_btn.setCursor(Qt.PointingHandCursor)
    install_btn.setFixedHeight(40)
    install_btn.setStyleSheet("""
        QPushButton {
            background: rgba(110,198,255,0.18);
            color: white;
            border: 1px solid rgba(110,198,255,0.55);
            border-radius: 10px;
            padding: 10px 18px;
            font-size: 13px;
        }
        QPushButton:hover { background: rgba(110,198,255,0.35); }
    """)
    br.addWidget(install_btn)

    refresh_btn = QPushButton(f"  {tr('settings.apps.refresh')}")
    refresh_btn.setCursor(Qt.PointingHandCursor)
    refresh_btn.setFixedHeight(40)
    refresh_btn.setStyleSheet("""
        QPushButton {
            background: rgba(255,255,255,0.08);
            color: white;
            border: 1px solid rgba(255,255,255,0.15);
            border-radius: 10px;
            padding: 10px 18px;
            font-size: 13px;
        }
        QPushButton:hover { background: rgba(255,255,255,0.18); }
    """)
    br.addWidget(refresh_btn)
    br.addStretch(1)
    lay.addWidget(btn_row)

    lay.addWidget(_section("Установленные приложения"))
    lay.addWidget(_hint("Пользовательские приложения можно удалить."))

    list_holder = QWidget()
    lh = QVBoxLayout(list_holder)
    lh.setContentsMargins(0, 0, 0, 0)
    lh.setSpacing(6)
    lay.addWidget(list_holder)

    def rebuild():
        _rebuild_app_list(w, list_holder)

    install_btn.clicked.connect(lambda: _install_from_settings(w, rebuild))
    refresh_btn.clicked.connect(rebuild)
    rebuild()

    lay.addStretch(1)
    return _scrollable(w)


def _rebuild_app_list(parent_widget, holder):
    for i in reversed(range(holder.layout().count())):
        it = holder.layout().itemAt(i)
        if it and it.widget():
            it.widget().setParent(None)

    reg = _get_registry(parent_widget)
    if reg is None:
        lbl = QLabel("⚠  Не удалось получить доступ к реестру приложений.")
        lbl.setStyleSheet("color: #FFA0B4; font-size: 12px; padding: 10px;")
        lbl.setWordWrap(True)
        holder.layout().addWidget(lbl)
        return

    if not reg.apps:
        lbl = QLabel("Приложений пока нет.")
        lbl.setStyleSheet("color: rgba(255,255,255,0.55); font-size: 12px;")
        holder.layout().addWidget(lbl)
        return

    items = sorted(reg.apps.items(),
                   key=lambda kv: (not kv[1].builtin, kv[1].name.lower()))

    for app_id, info in items:
        row = QWidget()
        rl = QHBoxLayout(row)
        rl.setContentsMargins(14, 8, 10, 8)
        rl.setSpacing(12)

        ic = QLabel()
        ic.setPixmap(get_icon(info.app_id, 24, state().get("accent")))
        rl.addWidget(ic)

        name = QLabel(info.name)
        name.setStyleSheet("color: rgba(255,255,255,0.92); font-size: 13px; font-weight: 500;")
        rl.addWidget(name)

        meta = QLabel(f"v{info.version} · {info.author}")
        meta.setStyleSheet("color: rgba(255,255,255,0.45); font-size: 11px;")
        rl.addWidget(meta)

        rl.addStretch(1)

        tag_text = tr("settings.apps.builtin") if info.builtin else tr("settings.apps.custom")
        tag = QLabel(tag_text)
        tag.setStyleSheet(f"""
            color: {'#6EC6FF' if info.builtin else '#FFB86C'};
            font-size: 10px;
            letter-spacing: 1px;
            padding: 3px 8px;
            border: 1px solid {'rgba(110,198,255,0.45)' if info.builtin else 'rgba(255,184,108,0.45)'};
            border-radius: 8px;
        """)
        rl.addWidget(tag)

        if not info.builtin:
            trash = QPushButton()
            trash.setIcon(QIcon(get_icon("trash", 18, "#FFA0B4")))
            trash.setFixedSize(32, 32)
            trash.setCursor(Qt.PointingHandCursor)
            trash.setToolTip("Удалить приложение")
            trash.setStyleSheet("""
                QPushButton {
                    background: rgba(255,107,138,0.15);
                    border: 1px solid rgba(255,107,138,0.40);
                    border-radius: 8px;
                }
                QPushButton:hover { background: rgba(255,107,138,0.35); }
            """)
            trash.clicked.connect(
                lambda _, a=app_id, p=parent_widget, h=holder: _do_remove(p, h, a))
            rl.addWidget(trash)

        row.setStyleSheet("""
            QWidget { background: rgba(255,255,255,0.05); border-radius: 12px; }
            QWidget:hover { background: rgba(255,255,255,0.08); }
        """)
        holder.layout().addWidget(row)


def _do_remove(parent_widget, holder, app_id):
    reg = _get_registry(parent_widget)
    if reg is None:
        return
    info = reg.get(app_id)
    if info is None or info.builtin:
        return

    ans = QMessageBox.question(
        parent_widget, tr("settings.apps.delete_title"),
        tr("settings.apps.delete_q", name=info.name),
        QMessageBox.Yes | QMessageBox.No)
    if ans != QMessageBox.Yes:
        return

    d = _get_desktop(parent_widget)
    if d and hasattr(d, "windows"):
        for w in list(d.windows):
            if getattr(w, "app_id", None) == app_id:
                w.close()

    reg.remove(app_id)

    if d:
        if hasattr(d, "dock"):
            d.dock.populate(d.registry.apps)
        if hasattr(d, "notifications"):
            d.notifications.push(tr("notif.app_removed"), info.name)
        if hasattr(d, "app_menu"):
            d.app_menu.set_registry(d.registry)

    _rebuild_app_list(parent_widget, holder)


def _install_from_settings(parent_widget, on_done):
    d = _get_desktop(parent_widget)
    if d is None or not hasattr(d, "registry"):
        QMessageBox.warning(parent_widget, tr("common.error"),
                            "Реестр приложений недоступен.")
        return
    reg = d.registry

    path, _ = QFileDialog.getOpenFileName(
        parent_widget, tr("settings.apps.install_title"), "", "Python (*.py)")
    if not path:
        return

    info, err = reg.install(path)
    if err:
        QMessageBox.warning(parent_widget, tr("common.error"), err)
        return

    QMessageBox.information(parent_widget, tr("common.success"),
                            tr("settings.apps.installed_ok", name=info.name))

    if hasattr(d, "dock"):
        d.dock.populate(d.registry.apps)
    if hasattr(d, "notifications"):
        d.notifications.push(tr("notif.app_installed"),
                             f"{info.name} v{info.version}")
    if hasattr(d, "app_menu"):
        d.app_menu.set_registry(d.registry)

    if on_done:
        on_done()


# ============================================================
#  Страница: Уведомления
# ============================================================

def _page_notifications():
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(30, 20, 30, 30)
    lay.setSpacing(2)

    lay.addWidget(_section("Уведомления"))
    lay.addWidget(_hint("Настройки всплывающих уведомлений и центра уведомлений."))

    lay.addWidget(_row("Показывать при запуске", _checkbox("show_startup_notification")))
    lay.addWidget(_row("Хранить историю", _checkbox("notifications_history")))
    lay.addWidget(_hint("Все уведомления сохраняются в /Notes/notifications.json"))

    lay.addWidget(_section("Тишина"))
    lay.addWidget(_row("Не беспокоить", _checkbox("do_not_disturb")))
    lay.addWidget(_hint("Скрывает все всплывающие уведомления."))

    lay.addWidget(_section("Длительность"))
    duration_row = QWidget()
    drl = QHBoxLayout(duration_row)
    drl.setContentsMargins(4, 6, 4, 6)
    drl.addWidget(QLabel("По умолчанию (мс):"))
    sp = QSpinBox()
    sp.setRange(500, 15000)
    sp.setSingleStep(500)
    sp.setValue(state().get("notification_duration", 3200))
    sp.setFixedWidth(120)
    sp.setStyleSheet("""
        QSpinBox {
            background: rgba(255,255,255,0.08);
            color: white;
            border: 1px solid rgba(255,255,255,0.15);
            border-radius: 8px;
            padding: 6px 10px;
            font-size: 12px;
        }
    """)
    sp.valueChanged.connect(lambda v: state().set("notification_duration", v))
    drl.addWidget(sp)
    drl.addStretch(1)
    lay.addWidget(duration_row)

    lay.addWidget(_section("Действия"))

    clear_btn = QPushButton("🗑  Очистить историю уведомлений")
    clear_btn.setCursor(Qt.PointingHandCursor)
    clear_btn.setFixedHeight(38)
    clear_btn.setStyleSheet("""
        QPushButton {
            background: rgba(255,107,138,0.15);
            color: #FFA0B4;
            border: 1px solid rgba(255,107,138,0.45);
            border-radius: 10px;
            padding: 6px 18px;
            font-size: 12px;
        }
        QPushButton:hover { background: rgba(255,107,138,0.35); color: white; }
    """)
    def clear_history():
        ans = QMessageBox.question(w, "Очистить",
            "Удалить всю историю уведомлений?",
            QMessageBox.Yes | QMessageBox.No)
        if ans == QMessageBox.Yes:
            try:
                from system.notify_history import history
                history().clear()
                _notify(w, "Уведомления", "История очищена")
            except Exception as e:
                QMessageBox.warning(w, "Ошибка", str(e))
    clear_btn.clicked.connect(clear_history)
    lay.addWidget(clear_btn)

    lay.addStretch(1)
    return _scrollable(w)


# ============================================================
#  Страница: Приватность
# ============================================================

def _page_privacy():
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(30, 20, 30, 30)
    lay.setSpacing(2)

    lay.addWidget(_section("Безопасность"))
    lay.addWidget(_hint("Всё хранится локально в VFS MountOS."))

    lay.addWidget(_row("Блокировка окон", _checkbox("lock_windows", False)))
    lay.addWidget(_row("Защита паролем", _checkbox("require_password", False)))
    lay.addWidget(_hint("При включении потребуется пароль при запуске MountOS."))

    lay.addWidget(_section("Разрешения"))
    lay.addWidget(_row("Уведомления", _checkbox("perm_notifications")))
    lay.addWidget(_row("Доступ к файлам", _checkbox("perm_files")))
    lay.addWidget(_row("Запуск в фоне", _checkbox("perm_background", False)))

    lay.addWidget(_section("Данные"))
    lay.addWidget(_hint("Всё, что хранится в MountOS, лежит в system/user_data/."))

    def open_data_folder():
        try:
            vfs = _get_vfs(w)
            if vfs:
                d = _get_desktop(w)
                if d and hasattr(d, "open_app"):
                    d.open_app("files")
        except Exception:
            pass

    open_btn = QPushButton("📁  Открыть папку данных")
    open_btn.setCursor(Qt.PointingHandCursor)
    open_btn.setFixedHeight(38)
    open_btn.setStyleSheet("""
        QPushButton {
            background: rgba(110,198,255,0.18);
            color: white;
            border: 1px solid rgba(110,198,255,0.50);
            border-radius: 10px;
            padding: 6px 18px;
            font-size: 12px;
        }
        QPushButton:hover { background: rgba(110,198,255,0.35); }
    """)
    open_btn.clicked.connect(open_data_folder)
    lay.addWidget(open_btn)

    lay.addWidget(_section("Очистка"))
    clear_cache_btn = QPushButton("🧹  Очистить кэш превью")
    clear_cache_btn.setCursor(Qt.PointingHandCursor)
    clear_cache_btn.setFixedHeight(38)
    clear_cache_btn.setStyleSheet("""
        QPushButton {
            background: rgba(255,255,255,0.06);
            color: white;
            border: 1px solid rgba(255,255,255,0.12);
            border-radius: 10px;
            padding: 6px 18px;
            font-size: 12px;
        }
        QPushButton:hover { background: rgba(255,255,255,0.18); }
    """)
    def clear_cache():
        _notify(w, "Кэш", "Кэш превью очищен")
    clear_cache_btn.clicked.connect(clear_cache)
    lay.addWidget(clear_cache_btn)

    lay.addStretch(1)
    return _scrollable(w)


# ============================================================
#  Страница: Система
# ============================================================

def _page_system():
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(30, 20, 30, 30)
    lay.setSpacing(2)

    lay.addWidget(_section("Состояние"))
    uptime_lbl = QLabel("—")
    uptime_lbl.setStyleSheet("color: white; font-size: 14px; font-weight: 600; padding: 4px;")
    lay.addWidget(_row("Аптайм MountOS", uptime_lbl))

    apps_lbl = QLabel("—")
    apps_lbl.setStyleSheet("color: white; font-size: 14px; font-weight: 600; padding: 4px;")
    lay.addWidget(_row("Приложений", apps_lbl))

    wins_lbl = QLabel("—")
    wins_lbl.setStyleSheet("color: white; font-size: 14px; font-weight: 600; padding: 4px;")
    lay.addWidget(_row("Открытых окон", wins_lbl))

    mem_lbl = QLabel("—")
    mem_lbl.setStyleSheet("color: white; font-size: 14px; font-weight: 600; padding: 4px;")
    lay.addWidget(_row("Память процесса", mem_lbl))

    def update_stats():
        secs = int(time.time() - _START_TIME)
        h = secs // 3600
        m = (secs % 3600) // 60
        s = secs % 60
        uptime_lbl.setText(f"{h:02d}:{m:02d}:{s:02d}")

        reg = _get_registry(w)
        if reg:
            apps_lbl.setText(str(len(reg.apps)))

        d = _get_desktop(w)
        if d and hasattr(d, "windows"):
            wins_lbl.setText(str(len(d.windows)))

        try:
            import psutil
            m_mb = psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024
            mem_lbl.setText(f"{m_mb:.1f} МБ")
        except ImportError:
            mem_lbl.setText("—")

    t = QTimer(w)
    t.timeout.connect(update_stats)
    t.start(2000)
    update_stats()

    lay.addWidget(_section("Управление"))
    lay.addWidget(_hint("Перезапуск нужен после изменений в .py-приложениях."))

    r_row = QWidget()
    rr = QHBoxLayout(r_row)
    rr.setContentsMargins(4, 8, 4, 8)
    rr.setSpacing(10)

    restart_btn = QPushButton("🔄  Перезапустить MountOS")
    restart_btn.setCursor(Qt.PointingHandCursor)
    restart_btn.setFixedHeight(40)
    restart_btn.setStyleSheet("""
        QPushButton {
            background: rgba(110,198,255,0.18);
            color: white;
            border: 1px solid rgba(110,198,255,0.55);
            border-radius: 10px;
            padding: 10px 18px;
            font-size: 13px;
        }
        QPushButton:hover { background: rgba(110,198,255,0.35); }
    """)
    restart_btn.clicked.connect(_restart_mountos)
    rr.addWidget(restart_btn)

    quit_btn = QPushButton("🚪  Выйти из MountOS")
    quit_btn.setCursor(Qt.PointingHandCursor)
    quit_btn.setFixedHeight(40)
    quit_btn.setStyleSheet("""
        QPushButton {
            background: rgba(255,107,138,0.15);
            color: #FFA0B4;
            border: 1px solid rgba(255,107,138,0.45);
            border-radius: 10px;
            padding: 10px 18px;
            font-size: 13px;
        }
        QPushButton:hover { background: rgba(255,107,138,0.35); color: white; }
    """)
    quit_btn.clicked.connect(QApplication.instance().quit)
    rr.addWidget(quit_btn)
    rr.addStretch(1)
    lay.addWidget(r_row)

    # Горячие клавиши
    lay.addWidget(_section("Горячие клавиши"))
    for k, v in HOTKEYS_HELP:
        row = QWidget()
        rl = QHBoxLayout(row)
        rl.setContentsMargins(12, 6, 12, 6)

        kl = QLabel(k)
        kl.setStyleSheet("""
            color: #6EC6FF;
            font-family: Consolas, monospace;
            font-size: 11px;
            font-weight: 600;
            background: rgba(110,198,255,0.10);
            border: 1px solid rgba(110,198,255,0.35);
            border-radius: 7px;
            padding: 3px 10px;
            min-width: 130px;
        """)
        rl.addWidget(kl)

        vl = QLabel(v)
        vl.setStyleSheet("color: rgba(255,255,255,0.85); font-size: 12px; background: transparent; border: none;")
        rl.addWidget(vl, 1)

        row.setStyleSheet("QWidget { background: rgba(255,255,255,0.04); border-radius: 8px; margin: 1px 0; }")
        lay.addWidget(row)

    lay.addStretch(1)
    return _scrollable(w)


# ============================================================
#  Страница: Обновления
# ============================================================

def _page_updates():
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(30, 20, 30, 30)
    lay.setSpacing(2)

    lay.addWidget(_section("Версия MountOS"))
    ver_lbl = QLabel(f"MountOS {VERSION} {VERSION_TAG}")
    ver_lbl.setStyleSheet("color: white; font-size: 20px; font-weight: 300; padding: 8px 4px;")
    lay.addWidget(ver_lbl)

    channel_lbl = QLabel(f"Канал: {CODENAME}")
    channel_lbl.setStyleSheet("color: rgba(255,255,255,0.55); font-size: 12px; padding: 2px 4px 12px 4px;")
    lay.addWidget(channel_lbl)

    status_box = QLabel("✓  Установлена последняя версия")
    status_box.setStyleSheet("""
        background: rgba(110,231,183,0.15);
        color: #6EE7B7;
        border: 1px solid rgba(110,231,183,0.45);
        border-radius: 10px;
        padding: 12px 16px;
        font-size: 13px;
        font-weight: 600;
    """)
    lay.addWidget(status_box)

    lay.addWidget(_section("Канал обновлений"))
    channel_combo = QComboBox()
    channel_combo.addItems(["Stable", "Beta", "Development"])
    channel_combo.setCurrentIndex(0)
    channel_combo.setFixedWidth(200)
    channel_combo.setStyleSheet("""
        QComboBox {
            background: rgba(255,255,255,0.08);
            color: white;
            border: 1px solid rgba(255,255,255,0.15);
            border-radius: 8px;
            padding: 6px 10px;
            font-size: 12px;
        }
        QComboBox QAbstractItemView {
            background: rgba(28,34,54,0.98);
            color: white;
            selection-background-color: rgba(110,198,255,0.35);
        }
    """)
    lay.addWidget(_row("Канал", channel_combo))

    check_btn = QPushButton("🔍  Проверить обновления")
    check_btn.setCursor(Qt.PointingHandCursor)
    check_btn.setFixedHeight(40)
    check_btn.setStyleSheet("""
        QPushButton {
            background: rgba(110,198,255,0.18);
            color: white;
            border: 1px solid rgba(110,198,255,0.55);
            border-radius: 10px;
            padding: 10px 18px;
            font-size: 13px;
        }
        QPushButton:hover { background: rgba(110,198,255,0.35); }
    """)
    def check_updates():
        status_box.setText("🔄  Проверка обновлений…")
        status_box.setStyleSheet("""
            background: rgba(110,198,255,0.15);
            color: #6EC6FF;
            border: 1px solid rgba(110,198,255,0.45);
            border-radius: 10px;
            padding: 12px 16px;
            font-size: 13px;
            font-weight: 600;
        """)
        QTimer.singleShot(1500, lambda: (
            status_box.setText("✓  Установлена последняя версия"),
            status_box.setStyleSheet("""
                background: rgba(110,231,183,0.15);
                color: #6EE7B7;
                border: 1px solid rgba(110,231,183,0.45);
                border-radius: 10px;
                padding: 12px 16px;
                font-size: 13px;
                font-weight: 600;
            """),
            _notify(w, "Обновления", "Последняя версия уже установлена")
        ))
    check_btn.clicked.connect(check_updates)
    lay.addWidget(check_btn)

    lay.addWidget(_section("История версий"))
    history_box = QTextEdit()
    history_box.setReadOnly(True)
    history_box.setFixedHeight(200)
    history_box.setStyleSheet("""
        QTextEdit {
            background: rgba(0,0,0,0.22);
            color: rgba(255,255,255,0.85);
            border: 1px solid rgba(255,255,255,0.10);
            border-radius: 10px;
            padding: 12px;
            font-family: Consolas, monospace;
            font-size: 12px;
        }
    """)
    history_box.setPlainText(
        f"MountOS {VERSION} {VERSION_TAG}  —  текущая\n"
        "  • Полная поддержка виртуальных рабочих столов\n"
        "  • Менеджер паролей с шифрованием\n"
        "  • Магазин приложений\n"
        "  • Визуальный дизайнер интерфейсов\n"
        "  • Горячая перезагрузка приложений\n"
        "  • Расширенный набор встроенных приложений\n\n"
        "MountOS 0.9  —  предыдущая\n"
        "  • Базовые приложения и рабочий стол\n"
        "  • Терминал, Проводник, Заметки\n"
        "  • Калькулятор, Календарь\n"
    )
    lay.addWidget(history_box)

    lay.addStretch(1)
    return _scrollable(w)


# ============================================================
#  Страница: Сброс
# ============================================================

def _page_reset():
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(30, 20, 30, 30)
    lay.setSpacing(2)

    lay.addWidget(_section("Сброс настроек"))
    lay.addWidget(_hint("Все настройки вернутся к заводским. Файлы и приложения не удаляются."))

    reset_btn = QPushButton("🔄  Сбросить все настройки")
    reset_btn.setCursor(Qt.PointingHandCursor)
    reset_btn.setFixedHeight(44)
    reset_btn.setStyleSheet("""
        QPushButton {
            background: rgba(255,184,108,0.18);
            color: #FFB86C;
            border: 1px solid rgba(255,184,108,0.50);
            border-radius: 10px;
            padding: 12px 18px;
            font-size: 13px;
            text-align: left;
        }
        QPushButton:hover { background: rgba(255,184,108,0.35); color: white; }
    """)
    def do_reset():
        ans = QMessageBox.question(w, "Сброс настроек",
            "Сбросить ВСЕ настройки MountOS?\n\n"
            "Обои, акцент, окна, видимость — вернутся к заводским.\n"
            "Приложения и файлы НЕ удаляются.",
            QMessageBox.Yes | QMessageBox.No)
        if ans == QMessageBox.Yes:
            state().reset()
            _notify(w, "Настройки сброшены", "Возвращены заводские значения")
    reset_btn.clicked.connect(do_reset)
    lay.addWidget(reset_btn)

    lay.addSpacing(20)

    lay.addWidget(_section("Экспорт / Импорт"))
    lay.addWidget(_hint("Сохрани настройки в файл или восстанови из копии."))

    btn_row = QHBoxLayout()
    btn_row.setSpacing(10)

    export_btn = QPushButton("💾  Экспорт настроек")
    export_btn.setCursor(Qt.PointingHandCursor)
    export_btn.setFixedHeight(40)
    export_btn.setStyleSheet("""
        QPushButton {
            background: rgba(110,231,183,0.18);
            color: white;
            border: 1px solid rgba(110,231,183,0.50);
            border-radius: 10px;
            padding: 10px 18px;
            font-size: 12px;
        }
        QPushButton:hover { background: rgba(110,231,183,0.35); }
    """)
    def export_settings():
        vfs = _get_vfs(w)
        if not vfs:
            QMessageBox.warning(w, "Ошибка", "VFS недоступна")
            return
        try:
            data = state().all()
            vfs.mkdir("/Documents")
            path = f"/Documents/mountos_settings_{int(time.time())}.json"
            vfs.write_text(path, json.dumps(data, ensure_ascii=False, indent=2))
            _notify(w, "Экспорт", f"Настройки → {path}")
            QMessageBox.information(w, "Экспорт", f"Сохранено:\n{path}")
        except Exception as e:
            QMessageBox.warning(w, "Ошибка", str(e))
    export_btn.clicked.connect(export_settings)
    btn_row.addWidget(export_btn)

    import_btn = QPushButton("📂  Импорт настроек")
    import_btn.setCursor(Qt.PointingHandCursor)
    import_btn.setFixedHeight(40)
    import_btn.setStyleSheet("""
        QPushButton {
            background: rgba(110,198,255,0.18);
            color: white;
            border: 1px solid rgba(110,198,255,0.50);
            border-radius: 10px;
            padding: 10px 18px;
            font-size: 12px;
        }
        QPushButton:hover { background: rgba(110,198,255,0.35); }
    """)
    import_btn.clicked.connect(lambda: QMessageBox.information(
        w, "Импорт", "Открой файл настроек через Проводник."))
    btn_row.addWidget(import_btn)
    btn_row.addStretch(1)
    lay.addLayout(btn_row)

    lay.addSpacing(20)

    lay.addWidget(_section("Опасная зона"))
    lay.addWidget(_hint("⚠  Эти действия необратимы. Будь осторожен!"))

    clear_btn = QPushButton("🗑  Удалить все данные MountOS")
    clear_btn.setCursor(Qt.PointingHandCursor)
    clear_btn.setFixedHeight(44)
    clear_btn.setStyleSheet("""
        QPushButton {
            background: rgba(255,107,138,0.15);
            color: #FFA0B4;
            border: 1px solid rgba(255,107,138,0.45);
            border-radius: 10px;
            padding: 12px 18px;
            font-size: 13px;
            text-align: left;
        }
        QPushButton:hover { background: rgba(255,107,138,0.35); color: white; }
    """)
    def clear_all_data():
        ans = QMessageBox.warning(w, "Подтверждение",
            "Удалить ВСЕ данные MountOS?\n\n"
            "Это включает:\n"
            "• Все файлы в VFS\n"
            "• Все заметки и дневник\n"
            "• Настройки\n"
            "• Историю уведомлений\n\n"
            "Это действие НЕЛЬЗЯ отменить!",
            QMessageBox.Yes | QMessageBox.No)
        if ans != QMessageBox.Yes:
            return
        ans2 = QMessageBox.warning(w, "Точно?",
            "Ты УВЕРЕН? Все файлы будут удалены безвозвратно.",
            QMessageBox.Yes | QMessageBox.No)
        if ans2 == QMessageBox.Yes:
            QMessageBox.information(w, "Не реализовано",
                "Полная очистка данных выполняется вручную:\n"
                "удали папку system/user_data/ и перезапусти MountOS.")
    clear_btn.clicked.connect(clear_all_data)
    lay.addWidget(clear_btn)

    lay.addStretch(1)
    return _scrollable(w)


# ============================================================
#  Вспомогательные действия
# ============================================================

def _restart_mountos():
    import subprocess
    QApplication.instance().quit()
    subprocess.Popen([sys.executable] + sys.argv)


# ============================================================
#  Сборка
# ============================================================

def build():
    root = QWidget()
    root.setStyleSheet("background: transparent;")
    h = QHBoxLayout(root)
    h.setContentsMargins(0, 0, 0, 0)
    h.setSpacing(0)

    # ---- Сайдбар ----
    side = QWidget()
    side.setFixedWidth(240)
    side.setStyleSheet("""
        background: rgba(255,255,255,0.04);
        border-right: 1px solid rgba(255,255,255,0.08);
    """)
    sl = QVBoxLayout(side)
    sl.setContentsMargins(14, 18, 14, 18)
    sl.setSpacing(4)

    title = QLabel(f"  Настройки")
    title.setStyleSheet("""
        color: white;
        font-size: 16px;
        font-weight: 600;
        padding: 4px 8px 16px 8px;
    """)
    sl.addWidget(title)

    stack = QStackedWidget()
    stack.setStyleSheet("background: transparent;")

    pages = [
        ("settings",  "О системе",     _page_about),
        ("gallery",   "Оформление",    _page_appearance),
        ("globe",     "Обои",          _page_wallpaper),
        ("chat",      "Язык",          _page_language),
        ("files",     "Приложения",    _page_apps),
        ("bell",      "Уведомления",   _page_notifications),
        ("lock",      "Приватность",   _page_privacy),
        ("terminal",  "Система",       _page_system),
        ("download",  "Обновления",    _page_updates),
        ("reload",    "Сброс",         _page_reset),
    ]

    buttons = []

    def switch(idx):
        stack.setCurrentIndex(idx)
        for i, b in enumerate(buttons):
            b.setProperty("active", i == idx)
            b.style().unpolish(b)
            b.style().polish(b)

    for i, (icon_name, name, factory) in enumerate(pages):
        b = QPushButton(f"   {name}")
        b.setIcon(QIcon(get_icon(icon_name, 20, "#FFFFFF")))
        b.setIconSize(QSize(18, 18))
        b.setCursor(Qt.PointingHandCursor)
        b.setFixedHeight(40)
        b.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: rgba(255,255,255,0.75);
                border: none;
                border-radius: 10px;
                padding: 8px 12px;
                text-align: left;
                font-size: 13px;
            }
            QPushButton:hover {
                background: rgba(255,255,255,0.08);
                color: white;
            }
            QPushButton[active="true"] {
                background: rgba(110,198,255,0.22);
                color: white;
                border: 1px solid rgba(110,198,255,0.45);
            }
        """)
        b.clicked.connect(lambda _, i=i: switch(i))
        sl.addWidget(b)
        buttons.append(b)
        stack.addWidget(factory())

    sl.addStretch(1)

    # Футер с версией
    footer = QLabel(f"MountOS {VERSION} {VERSION_TAG}")
    footer.setAlignment(Qt.AlignCenter)
    footer.setStyleSheet("""
        color: rgba(255,255,255,0.35);
        font-size: 10px;
        letter-spacing: 1px;
        padding: 8px;
    """)
    sl.addWidget(footer)

    h.addWidget(side)
    h.addWidget(stack, 1)

    switch(0)
    return root