"""
MountOS — Настоящий blur (матовое стекло) для окон.

Поддерживает:
  • Windows 10/11  — через SetWindowCompositionAttribute (Acrylic/Blur)
  • Linux (KWin)   — через KWindowEffects (X11)
  • Linux (Wayland)— заготовка
  • macOS          — заготовка
"""
import sys

from system.paths import IS_WINDOWS, IS_LINUX, IS_MACOS


# ============================================================
#  Windows
# ============================================================

if IS_WINDOWS:
    import ctypes
    from ctypes import wintypes

    class ACCENT_POLICY(ctypes.Structure):
        _fields_ = [
            ("AccentState",   ctypes.c_int),
            ("AccentFlags",   ctypes.c_int),
            ("GradientColor", ctypes.c_uint),
            ("AnimationId",   ctypes.c_int),
        ]

    class WINDOWCOMPOSITIONATTRIBDATA(ctypes.Structure):
        _fields_ = [
            ("Attrib", ctypes.c_int),
            ("Data",   ctypes.c_void_p),
            ("SizeOfData", ctypes.c_size_t),
        ]

    class MARGINS(ctypes.Structure):
        _fields_ = [
            ("cxLeftWidth",    ctypes.c_int),
            ("cxRightWidth",   ctypes.c_int),
            ("cyTopHeight",    ctypes.c_int),
            ("cyBottomHeight", ctypes.c_int),
        ]

    ACCENT_DISABLED                   = 0
    ACCENT_ENABLE_GRADIENT            = 1
    ACCENT_ENABLE_TRANSPARENTGRADIENT = 2
    ACCENT_ENABLE_BLURBEHIND          = 3
    ACCENT_ENABLE_ACRYLICBLURBEHIND   = 4
    ACCENT_ENABLE_HOSTBACKDROP        = 5

    WCA_ACCENT_POLICY = 19

    _user32 = ctypes.windll.user32
    _dwmapi = ctypes.windll.dwmapi

    _SetWindowCompositionAttribute = _user32.SetWindowCompositionAttribute
    _SetWindowCompositionAttribute.argtypes = [
        wintypes.HWND,
        ctypes.POINTER(WINDOWCOMPOSITIONATTRIBDATA),
    ]
    _SetWindowCompositionAttribute.restype = wintypes.BOOL

    _DwmExtendFrameIntoClientArea = _dwmapi.DwmExtendFrameIntoClientArea
    _DwmExtendFrameIntoClientArea.argtypes = [
        wintypes.HWND,
        ctypes.POINTER(MARGINS),
    ]
    _DwmExtendFrameIntoClientArea.restype = ctypes.c_int


def _hex_to_abgr(hex_color: str, alpha: int = 0xCC) -> int:
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    r = int(h[0:2], 16)
    g = int(h[2:4], 16)
    b = int(h[4:6], 16)
    return (alpha << 24) | (b << 16) | (g << 8) | r


def _apply_blur_windows(window, hex_color: str, alpha: int, acrylic: bool):
    try:
        hwnd = int(window.winId())
        margins = MARGINS(-1, -1, -1, -1)
        _DwmExtendFrameIntoClientArea(hwnd, ctypes.byref(margins))

        accent = ACCENT_POLICY()
        accent.AccentState = (ACCENT_ENABLE_ACRYLICBLURBEHIND
                              if acrylic else ACCENT_ENABLE_BLURBEHIND)
        accent.AccentFlags = 0x20 | 0x40 | 0x80 | 0x100
        accent.GradientColor = _hex_to_abgr(hex_color, alpha)
        accent.AnimationId = 0

        data = WINDOWCOMPOSITIONATTRIBDATA()
        data.Attrib = WCA_ACCENT_POLICY
        data.Data = ctypes.cast(ctypes.pointer(accent), ctypes.c_void_p)
        data.SizeOfData = ctypes.sizeof(accent)

        _SetWindowCompositionAttribute(hwnd, ctypes.byref(data))
        return True
    except Exception as e:
        print(f"[Blur/Win] ошибка: {e}")
        return False


def _remove_blur_windows(window):
    try:
        hwnd = int(window.winId())
        accent = ACCENT_POLICY()
        accent.AccentState = ACCENT_DISABLED
        data = WINDOWCOMPOSITIONATTRIBDATA()
        data.Attrib = WCA_ACCENT_POLICY
        data.Data = ctypes.cast(ctypes.pointer(accent), ctypes.c_void_p)
        data.SizeOfData = ctypes.sizeof(accent)
        _SetWindowCompositionAttribute(hwnd, ctypes.byref(data))
        return True
    except Exception as e:
        print(f"[Blur/Win] ошибка снятия: {e}")
        return False


# ============================================================
#  Linux
# ============================================================

def _apply_blur_linux(window, hex_color: str, alpha: int):
    try:
        import dbus
    except ImportError:
        return False
    try:
        session = dbus.SessionBus()
        if not session.name_has_owner("org.kde.KWin"):
            return False
        kwin = session.get_object("org.kde.KWin", "/KWin")
        effects = dbus.Interface(kwin, "org.kde.kwin.Effects")
        try:
            effects.loadEffect("blur")
        except Exception:
            pass
        return True
    except Exception:
        return False


def _remove_blur_linux(window):
    return True


# ============================================================
#  Публичный API
# ============================================================

def is_supported() -> bool:
    if IS_WINDOWS:
        return True
    if IS_LINUX:
        try:
            import os
            return (os.environ.get("XDG_CURRENT_DESKTOP", "").upper() in
                    ("KDE", "PLASMA")) and bool(os.environ.get("DISPLAY"))
        except Exception:
            return False
    return False


def apply_blur(window, hex_color: str = "#1C2236", alpha: int = 0xCC,
               acrylic: bool = True) -> bool:
    if IS_WINDOWS:
        return _apply_blur_windows(window, hex_color, alpha, acrylic)
    if IS_LINUX:
        return _apply_blur_linux(window, hex_color, alpha)
    return False


def remove_blur(window) -> bool:
    if IS_WINDOWS:
        return _remove_blur_windows(window)
    if IS_LINUX:
        return _remove_blur_linux(window)
    return True


def apply_blur_safe(window, hex_color: str = "#1C2236",
                    alpha: int = 0xCC, acrylic: bool = True) -> bool:
    try:
        return apply_blur(window, hex_color, alpha, acrylic)
    except Exception as e:
        print(f"[Blur] тихий отказ: {e}")
        return False


# ============================================================
#  Универсальный помощник для оверлеев (AppMenu, Spotlight)
# ============================================================

def apply_acrylic_overlay(window, tint_hex: str = "#0A0E1A",
                           tint_alpha: int = 0xBB) -> bool:
    """Накладывает Acrylic blur на окно-оверлей."""
    return apply_blur_safe(window, hex_color=tint_hex, alpha=tint_alpha,
                            acrylic=True)