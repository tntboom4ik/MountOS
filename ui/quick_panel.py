"""
MountOS — Панель быстрых настроек.

Выезжающая панель (как в Windows 11) с плитками-переключателями:
  • Wi-Fi (вкл/выкл — реально отключает через netsh / nmcli)
  • Bluetooth (вкл/выкл)
  • Звук (громкость слайдером)
  • Яркость (регулирует через WinAPI / xrandr)
  • Ночной режим (интеграция с night_mode)
  • Тёмная/светлая тема (интеграция с theme)
  • Не беспокоить (скрывает уведомления)
  • Полноэкранный режим
  • Отключение/перезагрузка/сон

Открывается: Ctrl+Alt+Q или кликом по индикаторам в панели.

API:
    from ui.quick_panel import QuickPanel
    panel = QuickPanel(host)
    panel.toggle()
"""

import os
import subprocess
import sys
from datetime import datetime

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                                QPushButton, QSlider, QGraphicsDropShadowEffect,
                                QGridLayout, QFrame, QSizePolicy)
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QPoint, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QBrush, QPen

from ui.icons import get_icon
from ui.settings_state import state
from system.system_monitor import monitor, IS_WINDOWS, IS_LINUX


PANEL_WIDTH = 400
PANEL_MARGIN = 12


# ============================================================
#  Хелперы для системных вызовов
# ============================================================

def _no_window_flags():
    """Флаги subprocess, чтобы не мелькала консоль на Windows."""
    if IS_WINDOWS:
        return subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
    return 0


def get_wifi_state() -> bool:
    """Возвращает True если Wi-Fi включён."""
    if IS_WINDOWS:
        try:
            result = subprocess.run(
                ["netsh", "interface", "show", "interface"],
                capture_output=True, text=True, timeout=2,
                creationflags=_no_window_flags())
            for line in result.stdout.splitlines():
                if "Wi-Fi" in line or "Беспроводн" in line:
                    if "Включ" in line or "Enabled" in line or "Connected" in line:
                        return True
                    return False
        except Exception:
            pass
    if IS_LINUX:
        try:
            result = subprocess.run(
                ["nmcli", "radio", "wifi"],
                capture_output=True, text=True, timeout=2)
            return result.stdout.strip() == "enabled"
        except Exception:
            pass
    return True   # Неизвестно — считаем что включён


def set_wifi_state(enabled: bool) -> bool:
    """Включает/выключает Wi-Fi. True если успешно."""
    if IS_WINDOWS:
        try:
            state_str = "enabled" if enabled else "disabled"
            subprocess.run(
                ["netsh", "interface", "set", "interface",
                 "Wi-Fi", f"admin={state_str}"],
                capture_output=True, timeout=3,
                creationflags=_no_window_flags())
            return True
        except Exception as e:
            print(f"[Quick] WiFi set: {e}")
    if IS_LINUX:
        try:
            state_str = "on" if enabled else "off"
            subprocess.run(["nmcli", "radio", "wifi", state_str],
                           capture_output=True, timeout=3)
            return True
        except Exception:
            pass
    return False


def get_bluetooth_state() -> bool:
    """True если Bluetooth включён."""
    if IS_WINDOWS:
        try:
            result = subprocess.run(
                ["powershell", "-Command",
                 "(Get-Service -Name bthserv).Status"],
                capture_output=True, text=True, timeout=3,
                creationflags=_no_window_flags())
            return "Running" in result.stdout
        except Exception:
            pass
    if IS_LINUX:
        try:
            result = subprocess.run(["rfkill", "list", "bluetooth"],
                                    capture_output=True, text=True, timeout=2)
            return "blocked: no" in result.stdout
        except Exception:
            pass
    return True


def set_bluetooth_state(enabled: bool) -> bool:
    """Включает/выключает Bluetooth."""
    if IS_WINDOWS:
        try:
            action = "Start-Service" if enabled else "Stop-Service"
            subprocess.run(
                ["powershell", "-Command",
                 f"{action} -Name bthserv"],
                capture_output=True, timeout=5,
                creationflags=_no_window_flags())
            return True
        except Exception:
            pass
    if IS_LINUX:
        try:
            action = "unblock" if enabled else "block"
            subprocess.run(["rfkill", action, "bluetooth"],
                           capture_output=True, timeout=3)
            return True
        except Exception:
            pass
    return False


def get_system_volume() -> int:
    """Возвращает текущую громкость Windows 0..100, или -1 если недоступна."""
    if IS_WINDOWS:
        try:
            from ctypes import cast, POINTER
            from comtypes import CLSCTX_ALL
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
            devices = AudioUtilities.GetSpeakers()
            interface = devices.Activate(IAudioEndpointVolume._iid_,
                                          CLSCTX_ALL, None)
            volume = cast(interface, POINTER(IAudioEndpointVolume))
            return int(volume.GetMasterVolumeLevelScalar() * 100)
        except Exception:
            pass
    return -1


def set_system_volume(percent: int) -> bool:
    """Устанавливает громкость Windows 0..100."""
    if IS_WINDOWS:
        try:
            from ctypes import cast, POINTER
            from comtypes import CLSCTX_ALL
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
            devices = AudioUtilities.GetSpeakers()
            interface = devices.Activate(IAudioEndpointVolume._iid_,
                                          CLSCTX_ALL, None)
            volume = cast(interface, POINTER(IAudioEndpointVolume))
            volume.SetMasterVolumeLevelScalar(max(0, min(1, percent / 100.0)), None)
            return True
        except Exception:
            pass
    return False


def get_brightness() -> int:
    """Возвращает яркость 0..100 или -1."""
    if IS_WINDOWS:
        try:
            result = subprocess.run(
                ["powershell", "-Command",
                 "(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightness).CurrentBrightness"],
                capture_output=True, text=True, timeout=3,
                creationflags=_no_window_flags())
            val = result.stdout.strip()
            if val.isdigit():
                return int(val)
        except Exception:
            pass
    if IS_LINUX:
        try:
            result = subprocess.run(
                ["brightnessctl", "get"],
                capture_output=True, text=True, timeout=2)
            max_r = subprocess.run(
                ["brightnessctl", "max"],
                capture_output=True, text=True, timeout=2)
            if result.returncode == 0 and max_r.returncode == 0:
                cur = int(result.stdout.strip())
                mx = int(max_r.stdout.strip())
                return int(cur / mx * 100)
        except Exception:
            pass
    return -1


def set_brightness(percent: int) -> bool:
    """Устанавливает яркость 0..100."""
    if IS_WINDOWS:
        try:
            subprocess.run(
                ["powershell", "-Command",
                 f"(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods).WmiSetBrightness(1, {percent})"],
                capture_output=True, timeout=3,
                creationflags=_no_window_flags())
            return True
        except Exception:
            pass
    if IS_LINUX:
        try:
            subprocess.run(["brightnessctl", "set", f"{percent}%"],
                           capture_output=True, timeout=2)
            return True
        except Exception:
            pass
    return False


# ============================================================
#  Плитка-переключатель
# ============================================================

class ToggleTile(QPushButton):
    """Плитка с иконкой и подписью, работает как переключатель."""

    toggled_custom = Signal(bool)

    def __init__(self, icon_name: str, title: str, parent=None,
                 initial: bool = False):
        super().__init__(parent)
        self.icon_name = icon_name
        self.title = title
        self._state = initial
        self.setCheckable(True)
        self.setChecked(initial)
        self.setCursor(Qt.PointingHandCursor)

        self.setFixedSize(110, 80)

        # Иконка + текст
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(4)

        self.icon_lbl = QLabel()
        self.icon_lbl.setAlignment(Qt.AlignCenter)
        self.icon_lbl.setStyleSheet("background: transparent; border: none;")
        lay.addWidget(self.icon_lbl)

        self.title_lbl = QLabel(title)
        self.title_lbl.setAlignment(Qt.AlignCenter)
        self.title_lbl.setStyleSheet("""
            color: white;
            font-size: 11px;
            font-weight: 500;
            background: transparent;
            border: none;
        """)
        lay.addWidget(self.title_lbl)

        self._refresh()
        self.clicked.connect(self._on_click)

    def _on_click(self):
        self._state = self.isChecked()
        self._refresh()
        self.toggled_custom.emit(self._state)

    def set_state(self, value: bool, silent: bool = False):
        self._state = bool(value)
        self.blockSignals(True)
        self.setChecked(self._state)
        self.blockSignals(False)
        self._refresh()
        if not silent:
            self.toggled_custom.emit(self._state)

    def get_state(self) -> bool:
        return self._state

    def _refresh(self):
        accent = state().get("accent", "#6EC6FF")
        if self._state:
            bg = f"rgba({self._hex_to_rgb(accent)}, 0.30)"
            border = f"1px solid rgba({self._hex_to_rgb(accent)}, 0.75)"
            icon_color = accent
        else:
            bg = "rgba(255, 255, 255, 0.06)"
            border = "1px solid rgba(255, 255, 255, 0.10)"
            icon_color = "#FFFFFF"

        self.setStyleSheet(f"""
            ToggleTile {{
                background: {bg};
                border: {border};
                border-radius: 14px;
            }}
            ToggleTile:hover {{
                background: rgba(255, 255, 255, 0.15);
            }}
            ToggleTile:pressed {{
                background: rgba(110, 198, 255, 0.35);
            }}
        """)

        pm = get_icon(self.icon_name, 26, icon_color)
        self.icon_lbl.setPixmap(pm)

    @staticmethod
    def _hex_to_rgb(h: str) -> str:
        h = h.lstrip("#")
        return f"{int(h[0:2], 16)}, {int(h[2:4], 16)}, {int(h[4:6], 16)}"


# ============================================================
#  Панель
# ============================================================

class QuickPanel(QWidget):
    """
    Выезжающая панель быстрых настроек.
    Открывается из панели или по Ctrl+Alt+Q.
    """

    def __init__(self, host: QWidget):
        super().__init__(host)
        self.host = host
        self.setFixedWidth(PANEL_WIDTH)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self._visible = False
        self.hide()

        # ---- Внешний контейнер с тенью ----
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, PANEL_MARGIN, PANEL_MARGIN, PANEL_MARGIN)
        outer.setSpacing(0)

        card = QWidget(self)
        card.setObjectName("quickCard")
        card.setStyleSheet("""
            QWidget#quickCard {
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
        cl.setSpacing(14)

        # ---- Заголовок ----
        header = QHBoxLayout()
        title = QLabel("Быстрые настройки")
        title.setStyleSheet("""
            color: white;
            font-size: 16px;
            font-weight: 600;
            letter-spacing: 0.5px;
        """)
        header.addWidget(title)
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

        # ---- Плитки (сетка 3 колонки) ----
        grid = QGridLayout()
        grid.setSpacing(8)

        # Wi-Fi
        self.wifi_tile = ToggleTile("globe", "Wi-Fi", initial=True)
        self.wifi_tile.toggled_custom.connect(self._on_wifi_toggle)
        grid.addWidget(self.wifi_tile, 0, 0)

        # Bluetooth
        self.bt_tile = ToggleTile("grid", "Bluetooth", initial=False)
        self.bt_tile.toggled_custom.connect(self._on_bt_toggle)
        grid.addWidget(self.bt_tile, 0, 1)

        # Ночной режим
        self.night_tile = ToggleTile("clock", "Ночной", initial=False)
        self.night_tile.toggled_custom.connect(self._on_night_toggle)
        grid.addWidget(self.night_tile, 0, 2)

        # Тема
        self.theme_tile = ToggleTile("star", "Тёмная", initial=True)
        self.theme_tile.toggled_custom.connect(self._on_theme_toggle)
        grid.addWidget(self.theme_tile, 1, 0)

        # Не беспокоить
        self.dnd_tile = ToggleTile("bell", "Тишина", initial=False)
        self.dnd_tile.toggled_custom.connect(self._on_dnd_toggle)
        grid.addWidget(self.dnd_tile, 1, 1)

        # Полноэкранный режим
        self.full_tile = ToggleTile("browser", "Полный", initial=False)
        self.full_tile.toggled_custom.connect(self._on_fullscreen_toggle)
        grid.addWidget(self.full_tile, 1, 2)

        cl.addLayout(grid)

        # ---- Слайдеры: громкость и яркость ----
        cl.addWidget(self._make_slider_block("Громкость", "music",
                                              self._on_volume_change,
                                              initial=50, key="volume"))
        cl.addWidget(self._make_slider_block("Яркость", "gallery",
                                              self._on_brightness_change,
                                              initial=70, key="brightness"))

        # ---- Системная информация ----
        info_box = QWidget()
        info_box.setStyleSheet("""
            QWidget {
                background: rgba(255,255,255,0.04);
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 12px;
            }
        """)
        il = QVBoxLayout(info_box)
        il.setContentsMargins(14, 10, 14, 10)
        il.setSpacing(4)

        self.battery_lbl = QLabel("Батарея: —")
        self.cpu_lbl = QLabel("CPU: —")
        self.ram_lbl = QLabel("RAM: —")
        self.uptime_lbl = QLabel("Аптайм: —")

        for lbl in (self.battery_lbl, self.cpu_lbl, self.ram_lbl, self.uptime_lbl):
            lbl.setStyleSheet("""
                color: rgba(255,255,255,0.75);
                font-size: 11px;
                background: transparent;
                border: none;
            """)
            il.addWidget(lbl)

        cl.addWidget(info_box)

        # ---- Кнопки питания ----
        power_row = QHBoxLayout()
        power_row.setSpacing(6)

        for label, icon, callback in [
            ("Сон", "clock", self._on_sleep),
            ("Блок", "star", self._on_lock),
            ("Перезагр", "reload", self._on_restart),
            ("Выкл", "trash", self._on_shutdown),
        ]:
            b = QPushButton(label)
            b.setCursor(Qt.PointingHandCursor)
            b.setFixedHeight(34)
            b.setStyleSheet("""
                QPushButton {
                    background: rgba(255,255,255,0.06);
                    color: rgba(255,255,255,0.85);
                    border: 1px solid rgba(255,255,255,0.10);
                    border-radius: 8px;
                    font-size: 11px;
                }
                QPushButton:hover {
                    background: rgba(255,255,255,0.18);
                    color: white;
                }
            """)
            b.clicked.connect(callback)
            power_row.addWidget(b)

        cl.addLayout(power_row)

        # ---- Позиционирование ----
        self._reposition()

        # ---- Таймер обновления ----
        self._update_timer = QTimer(self)
        self._update_timer.timeout.connect(self._refresh_status)
        self._update_timer.start(2000)

        # ---- Подписка на настройки ----
        state().changed.connect(self._on_settings)

        # Начальное состояние
        self._sync_tiles()

    # ------------------------------------------------------------
    #  Слайдер-блок
    # ------------------------------------------------------------

    def _make_slider_block(self, title: str, icon_name: str,
                            callback, initial: int = 50, key: str = ""):
        box = QWidget()
        box.setStyleSheet("""
            QWidget {
                background: rgba(255,255,255,0.04);
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 12px;
            }
        """)
        lay = QHBoxLayout(box)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(10)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(get_icon(icon_name, 18, "#FFFFFF"))
        icon_lbl.setFixedSize(22, 22)
        icon_lbl.setStyleSheet("background: transparent; border: none;")
        lay.addWidget(icon_lbl)

        title_lbl = QLabel(title)
        title_lbl.setFixedWidth(80)
        title_lbl.setStyleSheet("""
            color: rgba(255,255,255,0.85);
            font-size: 12px;
            background: transparent;
            border: none;
        """)
        lay.addWidget(title_lbl)

        slider = QSlider(Qt.Horizontal)
        slider.setRange(0, 100)
        slider.setValue(initial)
        slider.setStyleSheet("""
            QSlider::groove:horizontal {
                height: 4px;
                background: rgba(255,255,255,0.15);
                border-radius: 2px;
            }
            QSlider::sub-page:horizontal {
                background: #6EC6FF;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: white;
                width: 14px;
                margin: -5px 0;
                border-radius: 7px;
            }
            QSlider::handle:horizontal:hover { background: #A0DEFF; }
        """)
        lay.addWidget(slider, 1)

        pct = QLabel(f"{initial}%")
        pct.setFixedWidth(40)
        pct.setAlignment(Qt.AlignRight)
        pct.setStyleSheet("""
            color: white;
            font-size: 11px;
            background: transparent;
            border: none;
        """)
        lay.addWidget(pct)

        def on_change(v):
            pct.setText(f"{v}%")
            callback(v)

        slider.valueChanged.connect(on_change)

        # Сохраняем ссылки для доступа
        if key:
            setattr(self, f"_{key}_slider", slider)
            setattr(self, f"_{key}_pct", pct)

        return box

    # ------------------------------------------------------------
    #  Позиционирование
    # ------------------------------------------------------------

    def _reposition(self):
        h = self.host.height()
        # Панель сверху-справа (под верхней панелью)
        self.setFixedHeight(min(640, h - 2 * PANEL_MARGIN))
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
        self._sync_tiles()
        self._refresh_status()
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
    #  Синхронизация состояния плиток
    # ------------------------------------------------------------

    def _sync_tiles(self):
        """Читает текущее состояние системы и настроек, обновляет плитки."""
        # Wi-Fi
        try:
            self.wifi_tile.set_state(get_wifi_state(), silent=True)
        except Exception:
            pass

        # Bluetooth
        try:
            self.bt_tile.set_state(get_bluetooth_state(), silent=True)
        except Exception:
            pass

        # Ночной режим
        try:
            from system.night_mode import night
            self.night_tile.set_state(night().is_active(), silent=True)
        except Exception:
            pass

        # Тема
        try:
            from system.theme import theme
            is_dark = theme().is_dark()
            self.theme_tile.set_state(is_dark, silent=True)
            self.theme_tile.title_lbl.setText("Тёмная" if is_dark else "Светлая")
        except Exception:
            pass

        # Не беспокоить
        self.dnd_tile.set_state(state().get("do_not_disturb", False), silent=True)

        # Полный экран
        try:
            self.full_tile.set_state(self.host.isFullScreen(), silent=True)
        except Exception:
            pass

        # Громкость
        try:
            vol = get_system_volume()
            if vol >= 0 and hasattr(self, "_volume_slider"):
                self._volume_slider.blockSignals(True)
                self._volume_slider.setValue(vol)
                self._volume_slider.blockSignals(False)
                self._volume_pct.setText(f"{vol}%")
        except Exception:
            pass

        # Яркость
        try:
            br = get_brightness()
            if br >= 0 and hasattr(self, "_brightness_slider"):
                self._brightness_slider.blockSignals(True)
                self._brightness_slider.setValue(br)
                self._brightness_slider.blockSignals(False)
                self._brightness_pct.setText(f"{br}%")
        except Exception:
            pass

    # ------------------------------------------------------------
    #  Обработчики плиток
    # ------------------------------------------------------------

    def _on_wifi_toggle(self, enabled):
        ok = set_wifi_state(enabled)
        if not ok:
            self.wifi_tile.set_state(not enabled, silent=True)

    def _on_bt_toggle(self, enabled):
        ok = set_bluetooth_state(enabled)
        if not ok:
            self.bt_tile.set_state(not enabled, silent=True)

    def _on_night_toggle(self, enabled):
        try:
            from system.night_mode import night
            if enabled:
                night().enable()
            else:
                night().disable()
        except Exception as e:
            print(f"[Quick] night: {e}")

    def _on_theme_toggle(self, enabled):
        """enabled=True → тёмная, False → светлая."""
        try:
            from system.theme import theme
            theme().set_theme("dark" if enabled else "light")
            self.theme_tile.title_lbl.setText("Тёмная" if enabled else "Светлая")
        except Exception as e:
            print(f"[Quick] theme: {e}")

    def _on_dnd_toggle(self, enabled):
        state().set("do_not_disturb", enabled)
        # Если включили — уведомление
        try:
            d = self.host
            if hasattr(d, "notifications") and enabled:
                d.notifications.push("🔕 Не беспокоить",
                                      "Уведомления скрыты")
        except Exception:
            pass

    def _on_fullscreen_toggle(self, enabled):
        try:
            if enabled:
                self.host.showFullScreen()
            else:
                self.host.showNormal()
        except Exception:
            pass

    # ------------------------------------------------------------
    #  Обработчики слайдеров
    # ------------------------------------------------------------

    def _on_volume_change(self, value):
        set_system_volume(value)

    def _on_brightness_change(self, value):
        set_brightness(value)

    # ------------------------------------------------------------
    #  Питание
    # ------------------------------------------------------------

    def _on_sleep(self):
        if IS_WINDOWS:
            try:
                subprocess.run(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"],
                               creationflags=_no_window_flags())
            except Exception as e:
                print(f"[Quick] sleep: {e}")
        elif IS_LINUX:
            try:
                subprocess.run(["systemctl", "suspend"])
            except Exception:
                pass

    def _on_lock(self):
        if IS_WINDOWS:
            try:
                subprocess.run(["rundll32.exe", "user32.dll,LockWorkStation"],
                               creationflags=_no_window_flags())
            except Exception:
                pass
        elif IS_LINUX:
            try:
                subprocess.run(["loginctl", "lock-session"])
            except Exception:
                pass

    def _on_restart(self):
        from PySide6.QtWidgets import QMessageBox
        ans = QMessageBox.question(
            self, "Перезагрузка",
            "Перезагрузить компьютер?\nВсе несохранённые данные будут потеряны.",
            QMessageBox.Yes | QMessageBox.No)
        if ans != QMessageBox.Yes:
            return
        if IS_WINDOWS:
            try:
                subprocess.run(["shutdown", "/r", "/t", "5"],
                               creationflags=_no_window_flags())
            except Exception:
                pass
        elif IS_LINUX:
            try:
                subprocess.run(["systemctl", "reboot"])
            except Exception:
                pass

    def _on_shutdown(self):
        from PySide6.QtWidgets import QMessageBox
        ans = QMessageBox.question(
            self, "Выключение",
            "Выключить компьютер?\nВсе несохранённые данные будут потеряны.",
            QMessageBox.Yes | QMessageBox.No)
        if ans != QMessageBox.Yes:
            return
        if IS_WINDOWS:
            try:
                subprocess.run(["shutdown", "/s", "/t", "5"],
                               creationflags=_no_window_flags())
            except Exception:
                pass
        elif IS_LINUX:
            try:
                subprocess.run(["systemctl", "poweroff"])
            except Exception:
                pass

    # ------------------------------------------------------------
    #  Обновление системной информации
    # ------------------------------------------------------------

    def _refresh_status(self):
        if not self._visible:
            return
        try:
            bat = monitor().battery()
            if bat.get("present"):
                icon = "🔌" if bat.get("charging") else "🔋"
                self.battery_lbl.setText(f"{icon} Батарея: {bat['percent']}%")
            else:
                self.battery_lbl.setText("🔌 Питание от сети")

            cpu = monitor().cpu_percent()
            self.cpu_lbl.setText(f"⚙ CPU: {cpu:.0f}%")

            mem = monitor().memory()
            self.ram_lbl.setText(
                f"💾 RAM: {mem['used']} / {mem['total']} МБ ({mem['percent']:.0f}%)")

            up = monitor().uptime()
            self.uptime_lbl.setText(
                f"⏱ Аптайм: {monitor().fmt_uptime(up)}")
        except Exception as e:
            print(f"[Quick] status: {e}")

    # ------------------------------------------------------------
    #  Реакция на смену настроек
    # ------------------------------------------------------------

    def _on_settings(self, key, value):
        if key == "do_not_disturb":
            self.dnd_tile.set_state(value, silent=True)
        elif key == "accent":
            # Перерисовываем плитки под новый акцент
            for tile in (self.wifi_tile, self.bt_tile, self.night_tile,
                         self.theme_tile, self.dnd_tile, self.full_tile):
                tile._refresh()