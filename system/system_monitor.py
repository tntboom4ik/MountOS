"""
MountOS — Системный монитор.

Собирает реальные данные о системе:
  • CPU — загрузка процессора (%)
  • RAM — память (занято / всего, %)
  • Диск — занято / всего
  • Сеть — скорость отправки/получения
  • Батарея — уровень и зарядка
  • Аптайм системы
  • Температура (если доступна)

Работает кросс-платформенно:
  • Windows — через psutil (если есть) или ctypes
  • Linux   — через /proc и /sys
  • macOS   — через psutil или shell-команды

Использование:
    from system.system_monitor import monitor
    monitor.cpu_percent()      # 12.5
    monitor.memory()           # {"used": 8192, "total": 16384, "percent": 50.0}
    monitor.battery()          # {"percent": 78, "charging": True}
    monitor.disk()             # {"used": ..., "total": ..., "percent": ...}
    monitor.uptime()           # секунды с запуска системы
"""

import os
import sys
import time
import platform
import subprocess

from PySide6.QtCore import QObject, Signal, QTimer


# ============================================================
#  Определение платформы
# ============================================================

IS_WINDOWS = sys.platform.startswith("win")
IS_LINUX = sys.platform.startswith("linux")
IS_MACOS = sys.platform.startswith("darwin")


# ============================================================
#  Попытка импортировать psutil (опционально)
# ============================================================

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False


# ============================================================
#  Монитор системы
# ============================================================

class SystemMonitor(QObject):
    """
    Синглтон-монитор системы.
    Периодически обновляет метрики и эмитит signal.
    """

    updated = Signal(dict)   # словарь со всеми метриками

    def __init__(self):
        super().__init__()
        self._cache = {
            "cpu": 0.0,
            "memory": {"used": 0, "total": 0, "percent": 0.0},
            "disk": {"used": 0, "total": 0, "percent": 0.0},
            "battery": {"percent": -1, "charging": False, "present": False},
            "network": {"sent": 0, "recv": 0, "sent_rate": 0, "recv_rate": 0},
            "uptime": 0,
            "temperature": None,
            "platform": platform.system(),
            "has_psutil": HAS_PSUTIL,
        }

        self._last_net = {"sent": 0, "recv": 0, "time": time.time()}

        # Таймер обновления (каждые 2 сек)
        self._timer = QTimer(self)
        self._timer.setInterval(2000)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()

        # Первое обновление сразу
        self.refresh()

    # ------------------------------------------------------------
    #  Обновление метрик
    # ------------------------------------------------------------

    def refresh(self):
        """Обновляет все метрики и эмитит updated."""
        try:
            self._update_cpu()
            self._update_memory()
            self._update_disk()
            self._update_battery()
            self._update_network()
            self._update_uptime()
            self._update_temperature()
        except Exception as e:
            print(f"[Monitor] refresh: {e}")

        self.updated.emit(dict(self._cache))

    # ------------------------------------------------------------
    #  CPU
    # ------------------------------------------------------------

    def _update_cpu(self):
        # Способ 1 — psutil (самый точный)
        if HAS_PSUTIL:
            try:
                self._cache["cpu"] = psutil.cpu_percent(interval=None)
                return
            except Exception:
                pass

        # Способ 2 — Windows через wmic
        if IS_WINDOWS:
            try:
                result = subprocess.run(
                    ["wmic", "cpu", "get", "loadpercentage"],
                    capture_output=True, text=True, timeout=2,
                    creationflags=subprocess.CREATE_NO_WINDOW
                    if hasattr(subprocess, "CREATE_NO_WINDOW") else 0)
                for line in result.stdout.splitlines():
                    line = line.strip()
                    if line.isdigit():
                        self._cache["cpu"] = float(line)
                        return
            except Exception:
                pass

        # Способ 3 — Linux /proc/stat
        if IS_LINUX:
            try:
                with open("/proc/loadavg", "r") as f:
                    load = float(f.read().split()[0])
                # Приблизительно: load 1.0 = 100% на одно ядро
                cores = os.cpu_count() or 1
                self._cache["cpu"] = min(100.0, load / cores * 100)
                return
            except Exception:
                pass

        # Fallback — держим старое значение

    # ------------------------------------------------------------
    #  Память
    # ------------------------------------------------------------

    def _update_memory(self):
        # Способ 1 — psutil
        if HAS_PSUTIL:
            try:
                vm = psutil.virtual_memory()
                self._cache["memory"] = {
                    "used": vm.used // (1024 ** 2),      # в МБ
                    "total": vm.total // (1024 ** 2),
                    "percent": vm.percent,
                }
                return
            except Exception:
                pass

        # Способ 2 — Linux /proc/meminfo
        if IS_LINUX:
            try:
                with open("/proc/meminfo", "r") as f:
                    info = {}
                    for line in f:
                        parts = line.split(":")
                        if len(parts) == 2:
                            key = parts[0].strip()
                            val = parts[1].strip().split()[0]
                            info[key] = int(val)  # в КБ
                total = info.get("MemTotal", 0)
                available = info.get("MemAvailable", info.get("MemFree", 0))
                used = total - available
                self._cache["memory"] = {
                    "used": used // 1024,      # в МБ
                    "total": total // 1024,
                    "percent": round(used / total * 100, 1) if total else 0,
                }
                return
            except Exception:
                pass

        # Способ 3 — Windows через wmic
        if IS_WINDOWS:
            try:
                result = subprocess.run(
                    ["wmic", "OS", "get",
                     "FreePhysicalMemory,TotalVisibleMemorySize", "/Value"],
                    capture_output=True, text=True, timeout=2,
                    creationflags=subprocess.CREATE_NO_WINDOW
                    if hasattr(subprocess, "CREATE_NO_WINDOW") else 0)
                free = total = 0
                for line in result.stdout.splitlines():
                    line = line.strip()
                    if line.startswith("FreePhysicalMemory="):
                        free = int(line.split("=")[1]) // 1024  # МБ
                    elif line.startswith("TotalVisibleMemorySize="):
                        total = int(line.split("=")[1]) // 1024
                if total > 0:
                    used = total - free
                    self._cache["memory"] = {
                        "used": used,
                        "total": total,
                        "percent": round(used / total * 100, 1),
                    }
            except Exception:
                pass

    # ------------------------------------------------------------
    #  Диск
    # ------------------------------------------------------------

    def _update_disk(self):
        # Способ 1 — psutil
        if HAS_PSUTIL:
            try:
                # Берём основной раздел
                if IS_WINDOWS:
                    path = os.environ.get("SystemDrive", "C:") + "\\"
                else:
                    path = "/"
                usage = psutil.disk_usage(path)
                self._cache["disk"] = {
                    "used": usage.used // (1024 ** 3),    # ГБ
                    "total": usage.total // (1024 ** 3),
                    "percent": usage.percent,
                }
                return
            except Exception:
                pass

        # Способ 2 — Windows ctypes
        if IS_WINDOWS:
            try:
                import ctypes
                free = ctypes.c_ulonglong(0)
                total = ctypes.c_ulonglong(0)
                ctypes.windll.kernel32.GetDiskFreeSpaceExW(
                    ctypes.c_wchar_p("C:\\"),
                    None, ctypes.pointer(total), ctypes.pointer(free))
                total_gb = total.value // (1024 ** 3)
                free_gb = free.value // (1024 ** 3)
                used = total_gb - free_gb
                percent = round(used / total_gb * 100, 1) if total_gb else 0
                self._cache["disk"] = {
                    "used": used,
                    "total": total_gb,
                    "percent": percent,
                }
                return
            except Exception:
                pass

        # Способ 3 — shutil.disk_usage (стандартный, работает везде)
        try:
            import shutil
            path = "C:\\" if IS_WINDOWS else "/"
            usage = shutil.disk_usage(path)
            self._cache["disk"] = {
                "used": usage.used // (1024 ** 3),
                "total": usage.total // (1024 ** 3),
                "percent": round(usage.used / usage.total * 100, 1)
                          if usage.total else 0,
            }
        except Exception:
            pass

    # ------------------------------------------------------------
    #  Батарея
    # ------------------------------------------------------------

    def _update_battery(self):
        # Способ 1 — psutil
        if HAS_PSUTIL:
            try:
                bat = psutil.sensors_battery()
                if bat is not None:
                    self._cache["battery"] = {
                        "percent": int(bat.percent),
                        "charging": bool(bat.power_plugged),
                        "present": True,
                    }
                    return
                else:
                    self._cache["battery"] = {
                        "percent": -1, "charging": False, "present": False}
                    return
            except Exception:
                pass

        # Способ 2 — Windows через wmic
        if IS_WINDOWS:
            try:
                result = subprocess.run(
                    ["wmic", "path", "Win32_Battery", "get",
                     "EstimatedChargeRemaining,BatteryStatus"],
                    capture_output=True, text=True, timeout=2,
                    creationflags=subprocess.CREATE_NO_WINDOW
                    if hasattr(subprocess, "CREATE_NO_WINDOW") else 0)
                lines = result.stdout.strip().splitlines()
                if len(lines) >= 2:
                    parts = lines[1].split()
                    if len(parts) >= 2:
                        level = int(parts[0])
                        status = int(parts[1])
                        charging = status in (2, 6, 7, 8, 9, 11)
                        self._cache["battery"] = {
                            "percent": level,
                            "charging": charging,
                            "present": True,
                        }
                        return
            except Exception:
                pass

        # Способ 3 — Linux /sys/class/power_supply/
        if IS_LINUX:
            try:
                base = "/sys/class/power_supply"
                if os.path.isdir(base):
                    for entry in os.listdir(base):
                        cap_path = os.path.join(base, entry, "capacity")
                        status_path = os.path.join(base, entry, "status")
                        if os.path.exists(cap_path):
                            with open(cap_path) as f:
                                level = int(f.read().strip())
                            charging = False
                            if os.path.exists(status_path):
                                with open(status_path) as f:
                                    st = f.read().strip().lower()
                                charging = st in ("charging", "full")
                            self._cache["battery"] = {
                                "percent": level,
                                "charging": charging,
                                "present": True,
                            }
                            return
            except Exception:
                pass

        # Нет батареи
        self._cache["battery"] = {
            "percent": -1, "charging": False, "present": False}

    # ------------------------------------------------------------
    #  Сеть
    # ------------------------------------------------------------

    def _update_network(self):
        total_sent = 0
        total_recv = 0

        # Способ 1 — psutil
        if HAS_PSUTIL:
            try:
                net = psutil.net_io_counters()
                total_sent = net.bytes_sent
                total_recv = net.bytes_recv
            except Exception:
                pass

        # Способ 2 — Linux /proc/net/dev
        elif IS_LINUX:
            try:
                with open("/proc/net/dev", "r") as f:
                    for line in f.readlines()[2:]:
                        parts = line.split()
                        if len(parts) >= 10 and parts[0] != "lo:":
                            total_recv += int(parts[1])
                            total_sent += int(parts[9])
            except Exception:
                pass

        # Считаем скорость
        now = time.time()
        dt = now - self._last_net["time"]
        if dt > 0 and self._last_net["sent"] > 0:
            sent_rate = (total_sent - self._last_net["sent"]) / dt
            recv_rate = (total_recv - self._last_net["recv"]) / dt
        else:
            sent_rate = 0
            recv_rate = 0

        self._last_net = {
            "sent": total_sent,
            "recv": total_recv,
            "time": now,
        }

        self._cache["network"] = {
            "sent": total_sent,
            "recv": total_recv,
            "sent_rate": max(0, sent_rate),
            "recv_rate": max(0, recv_rate),
        }

    # ------------------------------------------------------------
    #  Аптайм системы
    # ------------------------------------------------------------

    def _update_uptime(self):
        # Способ 1 — psutil
        if HAS_PSUTIL:
            try:
                self._cache["uptime"] = int(time.time() - psutil.boot_time())
                return
            except Exception:
                pass

        # Способ 2 — Linux /proc/uptime
        if IS_LINUX:
            try:
                with open("/proc/uptime", "r") as f:
                    self._cache["uptime"] = int(float(f.read().split()[0]))
                return
            except Exception:
                pass

        # Способ 3 — Windows через ctypes
        if IS_WINDOWS:
            try:
                import ctypes
                self._cache["uptime"] = int(ctypes.windll.kernel32.GetTickCount64() / 1000)
                return
            except Exception:
                pass

    # ------------------------------------------------------------
    #  Температура (опционально)
    # ------------------------------------------------------------

    def _update_temperature(self):
        # Способ 1 — psutil sensors_temperatures
        if HAS_PSUTIL:
            try:
                temps = psutil.sensors_temperatures()
                if temps:
                    # Берём первый доступный сенсор
                    for name, entries in temps.items():
                        if entries:
                            self._cache["temperature"] = round(entries[0].current, 1)
                            return
            except Exception:
                pass

        # Способ 2 — Linux /sys/class/thermal
        if IS_LINUX:
            try:
                base = "/sys/class/thermal"
                if os.path.isdir(base):
                    for entry in os.listdir(base):
                        if entry.startswith("thermal_zone"):
                            temp_path = os.path.join(base, entry, "temp")
                            if os.path.exists(temp_path):
                                with open(temp_path) as f:
                                    val = int(f.read().strip())
                                if val > 1000:
                                    val = val / 1000.0  # мК → °C
                                self._cache["temperature"] = round(val, 1)
                                return
            except Exception:
                pass

        self._cache["temperature"] = None

    # ------------------------------------------------------------
    #  Публичный API (короткие методы)
    # ------------------------------------------------------------

    def cpu_percent(self) -> float:
        return self._cache["cpu"]

    def memory(self) -> dict:
        return dict(self._cache["memory"])

    def disk(self) -> dict:
        return dict(self._cache["disk"])

    def battery(self) -> dict:
        return dict(self._cache["battery"])

    def network(self) -> dict:
        return dict(self._cache["network"])

    def uptime(self) -> int:
        return self._cache["uptime"]

    def temperature(self):
        return self._cache["temperature"]

    def all(self) -> dict:
        return dict(self._cache)

    # ------------------------------------------------------------
    #  Утилиты форматирования
    # ------------------------------------------------------------

    @staticmethod
    def fmt_bytes(n) -> str:
        """Форматирует байты: 1234 → 1.2 KB."""
        n = float(n)
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if n < 1024:
                return f"{n:.1f} {unit}"
            n /= 1024
        return f"{n:.1f} PB"

    @staticmethod
    def fmt_rate(bps) -> str:
        """Форматирует скорость: 1234 → 1.2 KB/s."""
        return SystemMonitor.fmt_bytes(bps) + "/s"

    @staticmethod
    def fmt_uptime(secs: int) -> str:
        """Форматирует аптайм: 3661 → 1ч 1м."""
        secs = int(secs)
        d = secs // 86400
        h = (secs % 86400) // 3600
        m = (secs % 3600) // 60
        if d > 0:
            return f"{d}д {h}ч {m}м"
        if h > 0:
            return f"{h}ч {m}м"
        return f"{m}м"


# ============================================================
#  Синглтон
# ============================================================

_monitor_instance = None


def monitor() -> SystemMonitor:
    """Возвращает глобальный монитор системы."""
    global _monitor_instance
    if _monitor_instance is None:
        _monitor_instance = SystemMonitor()
    return _monitor_instance