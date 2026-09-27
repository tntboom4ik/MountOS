"""
MountOS — Своё логирование.
Все логи пишутся в system/logs/.
"""
import sys
import traceback
from datetime import datetime

from system import paths


class MountLogger:
    def __init__(self):
        self.log_file = paths.LOG_FILE
        self.error_file = paths.ERROR_LOG_FILE
        self._log_handle = None
        self._err_handle = None
        self._open_files()

    def _open_files(self):
        try:
            self._log_handle = open(self.log_file, "a", encoding="utf-8")
            self._err_handle = open(self.error_file, "a", encoding="utf-8")
        except Exception:
            self._log_handle = None
            self._err_handle = None

    def _timestamp(self) -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _write(self, handle, level: str, msg: str):
        if handle is None:
            return
        try:
            line = f"[{self._timestamp()}] [{level}] {msg}\n"
            handle.write(line)
            handle.flush()
        except Exception:
            pass

    def info(self, msg: str):
        self._write(self._log_handle, "INFO", msg)

    def warn(self, msg: str):
        self._write(self._log_handle, "WARN", msg)

    def error(self, msg: str, exc: Exception = None):
        if exc is not None:
            tb = traceback.format_exc()
            msg = f"{msg}\n{tb}"
        self._write(self._log_handle, "ERROR", msg)
        self._write(self._err_handle, "ERROR", msg)

    def debug(self, msg: str):
        self._write(self._log_handle, "DEBUG", msg)

    def close(self):
        try:
            if self._log_handle:
                self._log_handle.close()
            if self._err_handle:
                self._err_handle.close()
        except Exception:
            pass


_instance = None


def log() -> MountLogger:
    global _instance
    if _instance is None:
        _instance = MountLogger()
    return _instance


def install_excepthook():
    """Все необработанные исключения пишутся в наш лог."""
    def hook(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        tb = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        log().error(f"Необработанное исключение:\n{tb}")
        sys.stderr.write(tb)

    sys.excepthook = hook


def rotate_logs(max_size_mb: int = 5):
    """Если лог больше max_size_mb — переименовывает в .old."""
    for path in (paths.LOG_FILE, paths.ERROR_LOG_FILE):
        try:
            if path.exists() and path.stat().st_size > max_size_mb * 1024 * 1024:
                old = path.with_suffix(path.suffix + ".old")
                if old.exists():
                    old.unlink()
                path.rename(old)
        except Exception:
            pass