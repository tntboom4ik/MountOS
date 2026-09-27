"""
MountOS — Горячая перезагрузка приложений.

Позволяет обновлять код приложения без перезапуска MountOS:
  • Наблюдение за изменениями .py-файлов
  • Автоматическая перезагрузка модуля при изменении
  • Перезапуск открытых окон приложения
  • Уведомление через центр уведомлений
  • Ручное переключение (вкл/выкл)
  • Работа через QFileSystemWatcher

Как это работает:
  1. При открытии приложения вызывается register_app(app_id, filepath)
  2. Файл добавляется в watch-лист QFileSystemWatcher
  3. При изменении файла → reload_app(app_id)
  4. Модуль удаляется из sys.modules, загружается заново через importlib
  5. Все окна этого приложения закрываются
  6. Пользователь может открыть приложение заново — уже с новым кодом

API:
    from system.hot_reload import hot_reload
    hot_reload.register_app("myapp", "/path/to/myapp.py")
    hot_reload.enable()   # вкл
    hot_reload.disable()  # выкл
    hot_reload.is_enabled()
"""

import importlib.util
import os
import sys
import time

from PySide6.QtCore import QObject, Signal, QTimer, QFileSystemWatcher


class HotReload(QObject):
    """Менеджер горячей перезагрузки."""

    app_reloaded = Signal(str, bool, str)   # app_id, success, message
    app_changed = Signal(str)                # app_id (изменение в файле)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._enabled = True
        self._watched = {}       # filepath -> app_id
        self._apps = {}          # app_id -> {"path", "filepath"}
        self._watcher = QFileSystemWatcher(self)
        self._watcher.fileChanged.connect(self._on_file_changed)

        # Debounce — чтобы не перезагружать несколько раз при быстром сохранении
        self._pending = {}       # filepath -> timer
        self._debounce_ms = 500

    # ------------------------------------------------------------
    #  Управление
    # ------------------------------------------------------------

    def enable(self):
        self._enabled = True

    def disable(self):
        self._enabled = False

    def is_enabled(self) -> bool:
        return self._enabled

    def toggle(self):
        self._enabled = not self._enabled

    # ------------------------------------------------------------
    #  Регистрация приложений
    # ------------------------------------------------------------

    def register_app(self, app_id: str, filepath: str):
        """
        Регистрирует приложение для наблюдения.
        filepath — абсолютный путь к .py файлу.
        """
        if not filepath or not os.path.isfile(filepath):
            return
        filepath = os.path.abspath(filepath)

        self._apps[app_id] = {
            "app_id": app_id,
            "filepath": filepath,
        }

        # Добавляем в watcher
        if filepath not in self._watched:
            if filepath in self._watcher.files():
                self._watcher.removePath(filepath)
            self._watcher.addPath(filepath)
            self._watched[filepath] = app_id

    def unregister_app(self, app_id: str):
        """Убирает приложение из наблюдения."""
        if app_id not in self._apps:
            return
        filepath = self._apps[app_id]["filepath"]
        if filepath in self._watched:
            del self._watched[filepath]
            try:
                self._watcher.removePath(filepath)
            except Exception:
                pass
        del self._apps[app_id]

    def clear(self):
        """Убирает все приложения из наблюдения."""
        for f in list(self._watcher.files()):
            try:
                self._watcher.removePath(f)
            except Exception:
                pass
        self._watched.clear()
        self._apps.clear()

    # ------------------------------------------------------------
    #  Обработка изменения
    # ------------------------------------------------------------

    def _on_file_changed(self, filepath: str):
        """Вызывается QFileSystemWatcher когда файл изменён."""
        if not self._enabled:
            return

        # Debounce — если уже стоит таймер на этот файл, сбрасываем
        if filepath in self._pending:
            timer = self._pending[filepath]
            timer.stop()
            timer.start(self._debounce_ms)
            return

        # Создаём таймер
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda fp=filepath: self._do_reload(fp))
        self._pending[filepath] = timer
        timer.start(self._debounce_ms)

    def _do_reload(self, filepath: str):
        """Реальная перезагрузка после debounce."""
        if filepath in self._pending:
            del self._pending[filepath]

        if not self._enabled:
            return
        if filepath not in self._watched:
            return

        app_id = self._watched[filepath]
        if app_id not in self._apps:
            return

        # Watcher может потерять файл после сохранения (некоторые редакторы
        # делают atomic save через rename). Пере-добавляем.
        try:
            if filepath not in self._watcher.files():
                if os.path.isfile(filepath):
                    self._watcher.addPath(filepath)
        except Exception:
            pass

        # Если файл удалён — сообщаем
        if not os.path.isfile(filepath):
            self.app_reloaded.emit(app_id, False, "Файл удалён")
            return

        # Перезагрузка
        success, msg = self.reload_app(app_id)
        self.app_reloaded.emit(app_id, success, msg)

    # ------------------------------------------------------------
    #  Реальная перезагрузка
    # ------------------------------------------------------------

    def reload_app(self, app_id: str) -> tuple:
        """
        Перезагружает модуль приложения.
        Возвращает (success, message).
        """
        if app_id not in self._apps:
            return False, "Приложение не зарегистрировано"

        info = self._apps[app_id]
        filepath = info["filepath"]

        if not os.path.isfile(filepath):
            return False, "Файл не найден"

        # Находим модуль в sys.modules
        # app_loader использует уникальные имена вида mountos_app_<id>_<hash>
        loaded_module = None
        for name, mod in list(sys.modules.items()):
            if not name.startswith("mountos_app_"):
                continue
            mod_file = getattr(mod, "__file__", "")
            if mod_file and os.path.abspath(mod_file) == filepath:
                loaded_module = name
                break

        # Также ищем по app_id в имени
        if not loaded_module:
            for name in list(sys.modules.keys()):
                if name.startswith(f"mountos_app_{app_id}_"):
                    loaded_module = name
                    break

        # Удаляем из sys.modules
        removed = []
        if loaded_module:
            try:
                del sys.modules[loaded_module]
                removed.append(loaded_module)
            except Exception:
                pass

        # Также удаляем любые модули с тем же filepath
        for name, mod in list(sys.modules.items()):
            mod_file = getattr(mod, "__file__", "")
            if mod_file and os.path.abspath(mod_file) == filepath:
                if name not in removed:
                    try:
                        del sys.modules[name]
                        removed.append(name)
                    except Exception:
                        pass

        # Очищаем .pyc
        try:
            pycache = os.path.join(os.path.dirname(filepath), "__pycache__")
            if os.path.isdir(pycache):
                base = os.path.splitext(os.path.basename(filepath))[0]
                for f in os.listdir(pycache):
                    if f.startswith(base):
                        try:
                            os.remove(os.path.join(pycache, f))
                        except Exception:
                            pass
        except Exception:
            pass

        # Загружаем заново через importlib
        try:
            mod_name = f"mountos_app_{app_id}_{int(time.time())}"
            spec = importlib.util.spec_from_file_location(mod_name, filepath)
            module = importlib.util.module_from_spec(spec)
            sys.modules[mod_name] = module
            spec.loader.exec_module(module)

            # Проверяем build()
            if not hasattr(module, "build") or not callable(module.build):
                return False, "Нет функции build()"

            # Обновляем реестр MountOS
            updated_in_registry = False
            try:
                from PySide6.QtWidgets import QApplication
                for top in QApplication.topLevelWidgets():
                    if hasattr(top, "registry") and hasattr(top.registry, "apps"):
                        reg = top.registry
                        if app_id in reg.apps:
                            reg.apps[app_id].build_fn = module.build
                            # Обновим имя/иконку тоже
                            if hasattr(module, "APP_NAME"):
                                reg.apps[app_id].name = module.APP_NAME
                            if hasattr(module, "APP_ICON"):
                                reg.apps[app_id].icon = module.APP_ICON
                            if hasattr(module, "APP_VERSION"):
                                reg.apps[app_id].version = module.APP_VERSION
                            updated_in_registry = True
                            # Обновляем док
                            if hasattr(top, "dock"):
                                top.dock.populate(reg.apps)
                            break
                    # Fallback через desktop_ref
                    ref = getattr(top, "desktop_ref", None)
                    if ref is not None and hasattr(ref, "registry"):
                        reg = ref.registry
                        if app_id in reg.apps:
                            reg.apps[app_id].build_fn = module.build
                            updated_in_registry = True
                            if hasattr(ref, "dock"):
                                ref.dock.populate(reg.apps)
                            break
            except Exception as e:
                print(f"[HotReload] registry update: {e}")

            msg = "Перезагружено"
            if not updated_in_registry:
                msg = "Модуль перезагружен (реестр не обновлён)"
            return True, msg

        except SyntaxError as e:
            return False, f"Синтаксис: строка {e.lineno}, {e.msg}"
        except Exception as e:
            return False, f"Ошибка: {type(e).__name__}: {e}"

    # ------------------------------------------------------------
    #  Ручная перезагрузка
    # ------------------------------------------------------------

    def reload_all(self) -> int:
        """Перезагружает все зарегистрированные приложения. Возвращает число успешных."""
        count = 0
        for app_id in list(self._apps.keys()):
            success, _ = self.reload_app(app_id)
            if success:
                count += 1
        return count

    def get_registered(self) -> list:
        """Список зарегистрированных приложений."""
        return [
            {"app_id": app_id, "filepath": info["filepath"]}
            for app_id, info in self._apps.items()
        ]

    def stats(self) -> dict:
        return {
            "enabled": self._enabled,
            "registered": len(self._apps),
            "watching": len(self._watcher.files()),
        }


# ============================================================
#  Синглтон
# ============================================================

_instance = None


def hot_reload() -> HotReload:
    """Глобальный менеджер горячей перезагрузки."""
    global _instance
    if _instance is None:
        _instance = HotReload()
    return _instance