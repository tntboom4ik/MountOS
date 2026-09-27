"""
MountOS — Миграция данных в system/storage/.

Копирует всё из system/user_data/ в system/storage/user_data/.
Старую папку НЕ удаляет — это backup.
Запускать ОДИН раз из корня MountOS.
"""
import shutil
import sys
from pathlib import Path


def migrate():
    base = Path(__file__).resolve().parent

    old_dir = base / "system" / "user_data"
    new_dir = base / "system" / "storage" / "user_data"

    print("=" * 60)
    print("  MountOS — миграция данных")
    print("=" * 60)
    print(f"\n📁 Старая папка: {old_dir}")
    print(f"📁 Новая папка:  {new_dir}\n")

    if not old_dir.exists():
        print("⚠ Старой папки нет — миграция не нужна")
        print("✅ MountOS создаст всё сама при первом запуске")
        return True

    old_files = list(old_dir.rglob("*"))
    file_count = sum(1 for f in old_files if f.is_file())
    dir_count = sum(1 for f in old_files if f.is_dir())

    print(f"📊 Найдено: {file_count} файлов в {dir_count} папках")

    if file_count == 0 and dir_count == 0:
        print("⚠ Папка пустая — миграция не нужна")
        return True

    new_dir.mkdir(parents=True, exist_ok=True)

    copied = 0
    errors = []

    for src in old_files:
        rel = src.relative_to(old_dir)
        dst = new_dir / rel

        try:
            if src.is_dir():
                dst.mkdir(parents=True, exist_ok=True)
            else:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                copied += 1
        except Exception as e:
            errors.append(f"  {rel}: {e}")

    print(f"\n✅ Скопировано: {copied} файлов")
    if errors:
        print(f"\n⚠ Ошибки ({len(errors)}):")
        for e in errors[:10]:
            print(e)

    print("\n" + "=" * 60)
    print("  Миграция завершена")
    print("=" * 60)
    print(f"\n📁 Новые данные: {new_dir}")
    print(f"📁 Старые данные: {old_dir}  (можно удалить позже)")
    print("\n▶ Запусти MountOS: python main.py")
    print("▶ Если всё работает — удали старую папку:")
    print(f"     rmdir /s \"{old_dir}\"           (Windows)")
    print(f"     rm -rf \"{old_dir}\"              (Linux/macOS)")
    print()

    return True


if __name__ == "__main__":
    try:
        ok = migrate()
        sys.exit(0 if ok else 1)
    except Exception as e:
        print(f"\n❌ Ошибка миграции: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)