"""
MountOS Application Loader
Сканирует папки, находит .py-приложения, собирает реестр.
Приложение должно определить функцию build() -> QWidget.
Опционально: APP_NAME, APP_ICON, APP_VERSION, APP_AUTHOR.
"""
import importlib.util
import os
import sys
import traceback


class AppInfo:
    def __init__(self, app_id, name, icon, version, author, path, build_fn, builtin=False):
        self.app_id = app_id
        self.name = name
        self.icon = icon
        self.version = version
        self.author = author
        self.path = path
        self.build_fn = build_fn
        self.builtin = builtin


class AppLoader:
    def __init__(self):
        self.apps = {}   # app_id -> AppInfo
        self.errors = [] # список (path, error)

    def scan(self, folders):
        """folders: список (путь, builtin_flag)"""
        for folder, builtin in folders:
            if not os.path.isdir(folder):
                continue
            for fname in sorted(os.listdir(folder)):
                if not fname.endswith(".py") or fname.startswith("_"):
                    continue
                path = os.path.join(folder, fname)
                self._load_file(path, builtin)
        return self.apps

    def _load_file(self, path, builtin):
        app_id = os.path.splitext(os.path.basename(path))[0]
        try:
            # Уникальное имя модуля, чтобы не конфликтовало
            mod_name = f"mountos_app_{app_id}_{abs(hash(path))}"
            spec = importlib.util.spec_from_file_location(mod_name, path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[mod_name] = module
            spec.loader.exec_module(module)

            build_fn = getattr(module, "build", None)
            if not callable(build_fn):
                self.errors.append((path, "нет функции build()"))
                return

            info = AppInfo(
                app_id=app_id,
                name=getattr(module, "APP_NAME", app_id.capitalize()),
                icon=getattr(module, "APP_ICON", "📦"),
                version=getattr(module, "APP_VERSION", "1.0"),
                author=getattr(module, "APP_AUTHOR", "unknown"),
                path=path,
                build_fn=build_fn,
                builtin=builtin,
            )
            self.apps[app_id] = info

        except Exception as e:
            tb = traceback.format_exc()
            self.errors.append((path, f"{e}\n{tb}"))
            print(f"[MountOS] Ошибка загрузки {path}:\n{tb}")

    def install_from_file(self, src_path, dest_dir):
        """Копирует .py файл в папку пользовательских приложений и загружает его."""
        import shutil
        if not src_path.endswith(".py"):
            return None, "Файл должен иметь расширение .py"
        os.makedirs(dest_dir, exist_ok=True)
        dest = os.path.join(dest_dir, os.path.basename(src_path))
        shutil.copy2(src_path, dest)
        self._load_file(dest, builtin=False)
        app_id = os.path.splitext(os.path.basename(dest))[0]
        return self.apps.get(app_id), None

    def remove(self, app_id, user_dir):
        """Удаляет пользовательское приложение."""
        info = self.apps.get(app_id)
        if not info or info.builtin:
            return False
        try:
            os.remove(info.path)
        except Exception:
            pass
        self.apps.pop(app_id, None)
        return True