# MountOS — Изоляция

## Что где лежит

- `system/storage/` — **все данные пользователя** (VFS, настройки, уведомления)
- `system/storage/temp/` — временные файлы
- `system/logs/` — логи работы MountOS
- `system/user_apps/` — пользовательские приложения
- `assets/` — шрифты, иконки

## Что MountOS НЕ трогает

- ❌ `C:\Users\<user>\AppData\` (Windows)
- ❌ `~/.config/`, `~/.cache/`, `~/.local/` (Linux)
- ❌ Реестр Windows
- ❌ Системные шрифты (использует свои из `assets/fonts/`, если есть)
- ❌ Системные настройки Qt

## Перенос на другой компьютер

Скопируй **всю папку MountOS** — она самодостаточна.

```bash
# Windows → флешка
xcopy C:\MountOS\ E:\MountOS\ /E /I

# Linux → флешка
cp -r ~/MountOS /media/usb/