"""
MountOS — Определение платформы.

MountOS использует системную ОС ТОЛЬКО для запуска Python.
"""
import sys
import platform as _platform


def is_windows() -> bool:
    return sys.platform.startswith("win")


def is_linux() -> bool:
    return sys.platform.startswith("linux")


def is_macos() -> bool:
    return sys.platform.startswith("darwin")


def name() -> str:
    if is_windows():
        return "Windows"
    if is_linux():
        try:
            import os
            for f in ("/etc/os-release", "/etc/lsb-release"):
                if os.path.exists(f):
                    with open(f, encoding="utf-8") as fp:
                        for line in fp:
                            if line.startswith(("NAME=", "DISTRIB_ID=")):
                                return line.split("=", 1)[1].strip().strip('"')
        except Exception:
            pass
        return "Linux"
    if is_macos():
        return "macOS"
    return "Unknown"


def version() -> str:
    try:
        return _platform.release()
    except Exception:
        return "—"


def arch() -> str:
    return _platform.machine() or "—"


def python_version() -> str:
    return sys.version.split()[0]


def hostname() -> str:
    try:
        return _platform.node() or "—"
    except Exception:
        return "—"


def processor() -> str:
    try:
        return _platform.processor() or "—"
    except Exception:
        return "—"


def is_wayland() -> bool:
    if not is_linux():
        return False
    import os
    return os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland"


def is_x11() -> bool:
    if not is_linux():
        return False
    import os
    return bool(os.environ.get("DISPLAY"))


def desktop_environment() -> str:
    if not is_linux():
        return ""
    import os
    return os.environ.get("XDG_CURRENT_DESKTOP", "")


def is_virtual_machine() -> bool:
    try:
        if is_linux():
            with open("/sys/class/dmi/id/product_name", encoding="utf-8") as f:
                nm = f.read().lower()
            return any(x in nm for x in
                       ["virtualbox", "vmware", "qemu", "kvm", "hyper-v"])
        if is_windows():
            import subprocess
            result = subprocess.run(
                ["wmic", "computersystem", "get", "model"],
                capture_output=True, text=True, timeout=2,
                creationflags=subprocess.CREATE_NO_WINDOW
                if hasattr(subprocess, "CREATE_NO_WINDOW") else 0)
            return any(x in result.stdout.lower()
                       for x in ["virtualbox", "vmware", "virtual machine"])
    except Exception:
        pass
    return False


def full_info() -> list:
    return [
        ("Операционная система", name()),
        ("Версия ядра",          version()),
        ("Архитектура",          arch()),
        ("Процессор",            processor()),
        ("Имя компьютера",       hostname()),
        ("Python",               python_version()),
    ]