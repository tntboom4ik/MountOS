import os
from system.app_loader import AppLoader


class Registry:
    """Глобальный реестр приложений MountOS."""

    def __init__(self, base_dir):
        self.base_dir = base_dir
        self.loader = AppLoader()

        builtin_dir = os.path.join(base_dir, "apps")
        user_dir    = os.path.join(base_dir, "system", "user_apps")
        self.user_dir = user_dir

        self.loader.scan([
            (builtin_dir, True),
            (user_dir, False),
        ])

    @property
    def apps(self):
        return self.loader.apps

    def get(self, app_id):
        return self.loader.apps.get(app_id)

    def install(self, src_path):
        return self.loader.install_from_file(src_path, self.user_dir)

    def remove(self, app_id):
        return self.loader.remove(app_id, self.user_dir)

    def rescan(self):
        self.loader.apps.clear()
        self.loader.errors.clear()
        builtin_dir = os.path.join(self.base_dir, "apps")
        self.loader.scan([
            (builtin_dir, True),
            (self.user_dir, False),
        ])