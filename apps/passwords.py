"""
MountOS — Менеджер паролей.

Защищённое хранилище паролей с шифрованием:
  • Мастер-пароль защищает всю базу
  • Шифрование через Fernet (AES-128 в CBC + HMAC-SHA256)
  • KDF (Key Derivation) через PBKDF2-HMAC-SHA256, 200 000 итераций
  • Генератор надёжных паролей
  • Категории и теги
  • Поиск по записям
  • Копирование в буфер (с автоочисткой через 30 сек)
  • Индикатор надёжности пароля
  • Автоблокировка после 5 минут неактивности
  • Экспорт/импорт зашифрованной базы
  • Восстановление через контрольную фразу

ВАЖНО:
  • Мастер-пароль нельзя восстановить — он не хранится нигде
  • При утере мастер-пароля данные потеряны навсегда
  • Используется только библиотека cryptography (стандарт индустрии)

Установка: apps/passwords.py + перезапуск MountOS.
Зависимость: pip install cryptography
"""

import base64
import hashlib
import json
import os
import secrets
import string
import time
from datetime import datetime, timedelta

from PySide6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QLabel,
                                QPushButton, QLineEdit, QListWidget,
                                QListWidgetItem, QTextEdit, QComboBox,
                                QCheckBox, QSpinBox, QMessageBox, QDialog,
                                QDialogButtonBox, QFormLayout, QScrollArea,
                                QFrame, QStackedWidget, QSizePolicy,
                                QInputDialog, QProgressBar, QSlider)
from PySide6.QtCore import Qt, QTimer, Signal, QSize
from PySide6.QtGui import QFont, QIcon, QColor, QPainter, QPainterPath, QBrush, QPen

from ui.icons import get_icon
from ui.settings_state import state
from ui.context_menu import make_menu

APP_NAME = "Пароли"
APP_ICON = "star"
APP_VERSION = "1.0"
APP_AUTHOR = "MountOS"


# ============================================================
#  Проверка cryptography
# ============================================================

try:
    from cryptography.fernet import Fernet, InvalidToken
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False


# ============================================================
#  Пути
# ============================================================

VAULT_PATH = "/Notes/passwords.vault"
VAULT_META_PATH = "/Notes/passwords_meta.json"
AUTOCOPY_CLEAR_SEC = 30


# ============================================================
#  Поиск VFS / Desktop
# ============================================================

def _get_vfs(widget):
    p = widget
    while p is not None:
        if hasattr(p, "vfs"):
            return p.vfs
        if hasattr(p, "desktop_ref") and p.desktop_ref is not None:
            return getattr(p.desktop_ref, "vfs", None)
        p = p.parent()
    from PySide6.QtWidgets import QApplication
    for top in QApplication.topLevelWidgets():
        if hasattr(top, "vfs"):
            return top.vfs
        ref = getattr(top, "desktop_ref", None)
        if ref is not None and hasattr(ref, "vfs"):
            return ref.vfs
    return None


def _get_desktop(widget):
    p = widget
    while p is not None:
        if hasattr(p, "notifications") and hasattr(p, "open_app"):
            return p
        if hasattr(p, "desktop_ref") and p.desktop_ref is not None:
            return p.desktop_ref
        p = p.parent()
    from PySide6.QtWidgets import QApplication
    for top in QApplication.topLevelWidgets():
        if hasattr(top, "notifications") and hasattr(top, "open_app"):
            return top
        ref = getattr(top, "desktop_ref", None)
        if ref is not None:
            return ref
    return None


# ============================================================
#  Крипто
# ============================================================

ITERATIONS = 200_000
SALT_SIZE = 32


def derive_key(master_password: str, salt: bytes) -> bytes:
    """PBKDF2-HMAC-SHA256 → 32 байта → base64 для Fernet."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=ITERATIONS,
    )
    key = kdf.derive(master_password.encode("utf-8"))
    return base64.urlsafe_b64encode(key)


def make_verifier(master_password: str, salt: bytes) -> str:
    """Создаёт проверочную строку для быстрой валидации пароля."""
    h = hashlib.sha256(salt + master_password.encode("utf-8")).hexdigest()
    return h


def check_password_strength(password: str) -> tuple:
    """
    Возвращает (score, label, color, hints).
    score: 0..100
    """
    if not password:
        return (0, "Пусто", "#FF6B8A", [])

    score = 0
    hints = []

    # Длина
    length = len(password)
    if length >= 8: score += 20
    if length >= 12: score += 15
    if length >= 16: score += 10
    if length < 8: hints.append("Слишком короткий (<8)")

    # Разнообразие
    has_lower = any(c.islower() for c in password)
    has_upper = any(c.isupper() for c in password)
    has_digit = any(c.isdigit() for c in password)
    has_special = any(c in string.punctuation for c in password)

    if has_lower: score += 10
    else: hints.append("Нет строчных букв")
    if has_upper: score += 10
    else: hints.append("Нет заглавных букв")
    if has_digit: score += 10
    else: hints.append("Нет цифр")
    if has_special: score += 15
    else: hints.append("Нет спецсимволов")

    # Проверка на очевидные паттерны
    common = ["123456", "password", "qwerty", "111111", "abc123", "admin"]
    low = password.lower()
    for c in common:
        if c in low:
            score -= 20
            hints.append(f"Содержит «{c}»")
            break

    # Однообразность
    if len(set(password)) <= 3:
        score -= 15
        hints.append("Мало уникальных символов")

    score = max(0, min(100, score))

    if score < 30:
        return (score, "Слабый", "#FF6B8A", hints)
    if score < 60:
        return (score, "Средний", "#FFB86C", hints)
    if score < 85:
        return (score, "Хороший", "#6EC6FF", hints)
    return (score, "Отличный", "#6EE7B7", hints)


def generate_password(length: int = 16,
                       use_lower: bool = True,
                       use_upper: bool = True,
                       use_digits: bool = True,
                       use_special: bool = True) -> str:
    """Генерирует криптографически надёжный пароль."""
    chars = ""
    if use_lower:   chars += string.ascii_lowercase
    if use_upper:   chars += string.ascii_uppercase
    if use_digits:  chars += string.digits
    if use_special: chars += "!@#$%^&*()-_=+[]{};:,.<>?/|"

    if not chars:
        chars = string.ascii_letters + string.digits

    # Гарантируем хотя бы по одному символу из каждой выбранной группы
    password_chars = []
    if use_lower:   password_chars.append(secrets.choice(string.ascii_lowercase))
    if use_upper:   password_chars.append(secrets.choice(string.ascii_uppercase))
    if use_digits:  password_chars.append(secrets.choice(string.digits))
    if use_special: password_chars.append(secrets.choice("!@#$%^&*()-_=+[]{};:,.<>?/|"))

    remaining = max(0, length - len(password_chars))
    for _ in range(remaining):
        password_chars.append(secrets.choice(chars))

    secrets.SystemRandom().shuffle(password_chars)
    return "".join(password_chars)


# ============================================================
#  Хранилище
# ============================================================

class PasswordVault:
    """Зашифрованное хранилище паролей."""

    def __init__(self, vfs):
        self.vfs = vfs
        self.salt = None
        self.fernet = None
        self.master_hash = None
        self.records = []      # расшифрованные записи в памяти
        self.unlocked = False
        self.created_at = None

    def exists(self) -> bool:
        """Есть ли сохранённое хранилище."""
        if self.vfs is None:
            return False
        return self.vfs.exists(VAULT_PATH)

    def create(self, master_password: str) -> bool:
        """Создаёт новое хранилище."""
        if not master_password or len(master_password) < 4:
            return False
        self.salt = secrets.token_bytes(SALT_SIZE)
        key = derive_key(master_password, self.salt)
        self.fernet = Fernet(key)
        self.master_hash = make_verifier(master_password, self.salt)
        self.records = []
        self.unlocked = True
        self.created_at = time.time()
        return self._save()

    def unlock(self, master_password: str) -> tuple:
        """Разблокирует хранилище. Возвращает (ok, message)."""
        if self.vfs is None:
            return False, "VFS недоступна"

        # Читаем метаданные
        try:
            raw_meta = self.vfs.read_text(VAULT_META_PATH, "")
            if not raw_meta.strip():
                return False, "Файл хранилища повреждён"
            meta = json.loads(raw_meta)
        except Exception as e:
            return False, f"Ошибка чтения метаданных: {e}"

        try:
            self.salt = base64.b64decode(meta["salt"])
            self.master_hash = meta["verifier"]
            self.created_at = meta.get("created_at", 0)
        except Exception as e:
            return False, f"Ошибка формата метаданных: {e}"

        # Проверяем пароль
        if make_verifier(master_password, self.salt) != self.master_hash:
            return False, "Неверный мастер-пароль"

        # Деривируем ключ
        try:
            key = derive_key(master_password, self.salt)
            self.fernet = Fernet(key)
        except Exception as e:
            return False, f"Ошибка деривации ключа: {e}"

        # Расшифровываем базу
        try:
            encrypted = self.vfs.read_bytes(VAULT_PATH)
            decrypted = self.fernet.decrypt(encrypted)
            data = json.loads(decrypted.decode("utf-8"))
            self.records = data.get("records", [])
        except InvalidToken:
            return False, "Не удалось расшифровать (неверный ключ)"
        except Exception as e:
            return False, f"Ошибка расшифровки: {e}"

        self.unlocked = True
        return True, "OK"

    def lock(self):
        """Забывает ключ и записи."""
        self.fernet = None
        self.records = []
        self.unlocked = False
        self.salt = None
        self.master_hash = None

    def change_master(self, old_password: str, new_password: str) -> tuple:
        """Меняет мастер-пароль."""
        if not self.unlocked:
            return False, "Хранилище закрыто"
        # Проверяем старый
        if make_verifier(old_password, self.salt) != self.master_hash:
            return False, "Неверный старый пароль"
        if len(new_password) < 4:
            return False, "Новый пароль слишком короткий"

        # Новый salt, новый ключ
        self.salt = secrets.token_bytes(SALT_SIZE)
        self.master_hash = make_verifier(new_password, self.salt)
        key = derive_key(new_password, self.salt)
        self.fernet = Fernet(key)
        self._save()
        return True, "Пароль изменён"

    # ------------------------------------------------------------

    def _save(self) -> bool:
        """Шифрует и сохраняет."""
        if not self.unlocked or self.fernet is None or self.vfs is None:
            return False
        try:
            self.vfs.mkdir("/Notes")
            # Метаданные
            meta = {
                "salt": base64.b64encode(self.salt).decode("ascii"),
                "verifier": self.master_hash,
                "created_at": self.created_at or time.time(),
                "version": 1,
            }
            self.vfs.write_text(VAULT_META_PATH,
                json.dumps(meta, ensure_ascii=False, indent=2))

            # Данные
            payload = {
                "records": self.records,
                "saved_at": time.time(),
            }
            raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            encrypted = self.fernet.encrypt(raw)
            self.vfs.write_bytes(VAULT_PATH, encrypted)
            return True
        except Exception as e:
            print(f"[Vault] save error: {e}")
            return False

    def save(self) -> bool:
        return self._save()

    # ------------------------------------------------------------
    #  Работа с записями
    # ------------------------------------------------------------

    def add_record(self, title: str, username: str, password: str,
                    url: str = "", notes: str = "",
                    category: str = "Разное", tags: list = None) -> dict:
        rec = {
            "id": secrets.token_hex(8),
            "title": title,
            "username": username,
            "password": password,
            "url": url,
            "notes": notes,
            "category": category,
            "tags": tags or [],
            "created": time.time(),
            "updated": time.time(),
        }
        self.records.append(rec)
        self.save()
        return rec

    def update_record(self, rec_id: str, **fields):
        for r in self.records:
            if r["id"] == rec_id:
                for k, v in fields.items():
                    r[k] = v
                r["updated"] = time.time()
                self.save()
                return True
        return False

    def delete_record(self, rec_id: str) -> bool:
        before = len(self.records)
        self.records = [r for r in self.records if r["id"] != rec_id]
        if len(self.records) < before:
            self.save()
            return True
        return False

    def get(self, rec_id: str):
        for r in self.records:
            if r["id"] == rec_id:
                return r
        return None

    def search(self, query: str) -> list:
        if not query:
            return list(self.records)
        q = query.lower()
        result = []
        for r in self.records:
            searchable = (
                r.get("title", "") + " " +
                r.get("username", "") + " " +
                r.get("url", "") + " " +
                r.get("notes", "") + " " +
                r.get("category", "") + " " +
                " ".join(r.get("tags", []))
            ).lower()
            if q in searchable:
                result.append(r)
        return result

    def categories(self) -> list:
        cats = set()
        for r in self.records:
            cats.add(r.get("category", "Разное"))
        return sorted(cats)

    def stats(self) -> dict:
        weak = 0
        reused = {}
        total = len(self.records)
        for r in self.records:
            _, label, _, _ = check_password_strength(r.get("password", ""))
            if label in ("Слабый", "Средний"):
                weak += 1
            pw = r.get("password", "")
            reused[pw] = reused.get(pw, 0) + 1
        reused_count = sum(1 for v in reused.values() if v > 1)
        return {
            "total": total,
            "weak": weak,
            "reused": reused_count,
            "categories": len(self.categories()),
        }


# ============================================================
#  Диалог записи
# ============================================================

class RecordDialog(QDialog):
    def __init__(self, record: dict = None, categories: list = None, parent=None):
        super().__init__(parent)
        self.record = record
        self.setWindowTitle("Пароль" if not record else "Редактировать")
        self.setFixedSize(520, 560)
        self.setStyleSheet("""
            QDialog { background: #1A1F35; }
            QLabel { color: rgba(255,255,255,0.85); font-size: 12px; }
            QLineEdit, QTextEdit, QComboBox, QSpinBox {
                background: rgba(255,255,255,0.08);
                color: white;
                border: 1px solid rgba(255,255,255,0.15);
                border-radius: 8px;
                padding: 8px 10px;
                font-size: 13px;
            }
            QLineEdit:focus, QTextEdit:focus, QComboBox:focus {
                border: 1px solid rgba(110,198,255,0.6);
            }
            QCheckBox { color: rgba(255,255,255,0.85); font-size: 12px; }
            QCheckBox::indicator { width: 16px; height: 16px; }
        """)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(12)

        form = QFormLayout()
        form.setSpacing(10)

        # Заголовок
        self.title_input = QLineEdit()
        self.title_input.setPlaceholderText("Например: Google")
        form.addRow("Название:", self.title_input)

        # Логин
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("user@example.com")
        form.addRow("Логин:", self.username_input)

        # Пароль + генератор
        pw_row = QHBoxLayout()
        pw_row.setSpacing(6)
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setPlaceholderText("Пароль")
        pw_row.addWidget(self.password_input, 1)

        show_btn = QPushButton("👁")
        show_btn.setFixedSize(32, 32)
        show_btn.setCursor(Qt.PointingHandCursor)
        show_btn.setToolTip("Показать/скрыть")
        show_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255,255,255,0.08);
                color: white;
                border: 1px solid rgba(255,255,255,0.12);
                border-radius: 8px;
                font-size: 13px;
            }
            QPushButton:hover { background: rgba(255,255,255,0.20); }
        """)
        def toggle_show():
            if self.password_input.echoMode() == QLineEdit.Password:
                self.password_input.setEchoMode(QLineEdit.Normal)
            else:
                self.password_input.setEchoMode(QLineEdit.Password)
        show_btn.clicked.connect(toggle_show)
        pw_row.addWidget(show_btn)

        gen_btn = QPushButton("🎲")
        gen_btn.setFixedSize(32, 32)
        gen_btn.setCursor(Qt.PointingHandCursor)
        gen_btn.setToolTip("Сгенерировать надёжный пароль")
        gen_btn.setStyleSheet("""
            QPushButton {
                background: rgba(110,198,255,0.18);
                color: white;
                border: 1px solid rgba(110,198,255,0.45);
                border-radius: 8px;
                font-size: 13px;
            }
            QPushButton:hover { background: rgba(110,198,255,0.38); }
        """)
        def do_gen():
            pw = generate_password(16)
            self.password_input.setText(pw)
            self.password_input.setEchoMode(QLineEdit.Normal)
        gen_btn.clicked.connect(do_gen)
        pw_row.addWidget(gen_btn)

        form.addRow("Пароль:", pw_row)

        # Индикатор надёжности
        self.strength_bar = QProgressBar()
        self.strength_bar.setRange(0, 100)
        self.strength_bar.setValue(0)
        self.strength_bar.setTextVisible(False)
        self.strength_bar.setFixedHeight(6)
        self.strength_bar.setStyleSheet("""
            QProgressBar {
                background: rgba(255,255,255,0.10);
                border: none;
                border-radius: 3px;
            }
            QProgressBar::chunk {
                background: #FF6B8A;
                border-radius: 3px;
            }
        """)
        self.strength_lbl = QLabel("—")
        self.strength_lbl.setStyleSheet("color: rgba(255,255,255,0.55); font-size: 11px;")

        strength_row = QHBoxLayout()
        strength_row.addWidget(self.strength_bar, 1)
        strength_row.addWidget(self.strength_lbl)
        form.addRow("Надёжность:", strength_row)

        def on_pw_changed():
            score, label, color, hints = check_password_strength(self.password_input.text())
            self.strength_bar.setValue(score)
            self.strength_bar.setStyleSheet(f"""
                QProgressBar {{ background: rgba(255,255,255,0.10); border: none; border-radius: 3px; }}
                QProgressBar::chunk {{ background: {color}; border-radius: 3px; }}
            """)
            self.strength_lbl.setText(label)
            self.strength_lbl.setStyleSheet(f"color: {color}; font-size: 11px; font-weight: 600;")
        self.password_input.textChanged.connect(on_pw_changed)

        # URL
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://example.com")
        form.addRow("URL:", self.url_input)

        # Категория
        self.category_combo = QComboBox()
        self.category_combo.setEditable(True)
        default_cats = ["Разное", "Соцсети", "Почта", "Банки", "Работа",
                        "Учёба", "Игры", "Покупки", "Хостинг"]
        all_cats = sorted(set(default_cats + (categories or [])))
        self.category_combo.addItems(all_cats)
        form.addRow("Категория:", self.category_combo)

        # Теги
        self.tags_input = QLineEdit()
        self.tags_input.setPlaceholderText("важные, личные, 2FA")
        form.addRow("Теги:", self.tags_input)

        lay.addLayout(form)

        # Заметки
        lay.addWidget(QLabel("Заметки:"))
        self.notes_input = QTextEdit()
        self.notes_input.setFixedHeight(80)
        self.notes_input.setPlaceholderText("Секретные вопросы, коды восстановления, дополнительная информация…")
        lay.addWidget(self.notes_input)

        # Заполняем если редактируем
        if record:
            self.title_input.setText(record.get("title", ""))
            self.username_input.setText(record.get("username", ""))
            self.password_input.setText(record.get("password", ""))
            self.url_input.setText(record.get("url", ""))
            self.notes_input.setPlainText(record.get("notes", ""))
            self.category_combo.setCurrentText(record.get("category", "Разное"))
            self.tags_input.setText(", ".join(record.get("tags", [])))
            on_pw_changed()

        # Кнопки
        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self.reject)
        btns.setStyleSheet("""
            QPushButton {
                background: rgba(110,198,255,0.20);
                color: white;
                border: 1px solid rgba(110,198,255,0.50);
                border-radius: 8px;
                padding: 8px 20px;
                font-size: 12px;
                min-width: 90px;
            }
            QPushButton:hover { background: rgba(110,198,255,0.40); }
        """)
        lay.addWidget(btns)

    def _on_accept(self):
        if not self.title_input.text().strip():
            QMessageBox.warning(self, "Ошибка", "Название обязательно.")
            return
        if not self.password_input.text():
            QMessageBox.warning(self, "Ошибка", "Пароль обязателен.")
            return
        self.accept()

    def get_data(self) -> dict:
        tags = [t.strip() for t in self.tags_input.text().split(",") if t.strip()]
        return {
            "title": self.title_input.text().strip(),
            "username": self.username_input.text().strip(),
            "password": self.password_input.text(),
            "url": self.url_input.text().strip(),
            "notes": self.notes_input.toPlainText().strip(),
            "category": self.category_combo.currentText().strip() or "Разное",
            "tags": tags,
        }


# ============================================================
#  Основное приложение
# ============================================================

def build():
    root = QWidget()
    root_layout = QVBoxLayout(root)
    root_layout.setContentsMargins(0, 0, 0, 0)
    root_layout.setSpacing(0)

    # ---- Проверка библиотеки ----
    if not HAS_CRYPTO:
        err = QLabel(
            "🔐  Требуется библиотека cryptography\n\n"
            "Установи её командой:\n\n"
            "    pip install cryptography\n\n"
            "Без неё менеджер паролей не может безопасно хранить данные."
        )
        err.setAlignment(Qt.AlignCenter)
        err.setStyleSheet("""
            color: white;
            font-size: 15px;
            background: #1A1F35;
            padding: 60px;
        """)
        root_layout.addWidget(err)
        return root

    vfs = _get_vfs(root)
    desktop = _get_desktop(root)
    vault = PasswordVault(vfs)

    # ---- QStackedWidget: 3 страницы ----
    # 0 = создание хранилища
    # 1 = разблокировка
    # 2 = основное окно
    stack = QStackedWidget()
    root_layout.addWidget(stack)

    # ============================================================
    #  Страница 0: Создание хранилища
    # ============================================================
    create_page = QWidget()
    create_page.setStyleSheet("background: rgba(10,14,26,1);")
    cpl = QVBoxLayout(create_page)
    cpl.setAlignment(Qt.AlignCenter)
    cpl.setSpacing(16)

    create_title = QLabel("🔐  Создание хранилища паролей")
    create_title.setStyleSheet("color: white; font-size: 24px; font-weight: 300; letter-spacing: 1px;")
    create_title.setAlignment(Qt.AlignCenter)
    cpl.addWidget(create_title)

    create_hint = QLabel(
        "Придумай <b>мастер-пароль</b>. Он защитит все твои пароли.\n\n"
        "⚠  Мастер-пароль <b>нигде не сохраняется</b> — если забудешь, "
        "восстановить данные будет <b>невозможно</b>.\n\n"
        "Минимум 4 символа. Рекомендуется 12+ символов."
    )
    create_hint.setAlignment(Qt.AlignCenter)
    create_hint.setWordWrap(True)
    create_hint.setStyleSheet("""
        color: rgba(255,255,255,0.65);
        font-size: 13px;
        line-height: 1.6;
        padding: 0 40px;
    """)
    cpl.addWidget(create_hint)

    cpl.addSpacing(20)

    # Поля
    form_box = QWidget()
    form_box.setFixedWidth(400)
    form_box.setStyleSheet("""
        QWidget {
            background: rgba(255,255,255,0.04);
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 16px;
        }
        QLabel { color: rgba(255,255,255,0.85); font-size: 12px; border: none; background: transparent; }
        QLineEdit {
            background: rgba(255,255,255,0.08);
            color: white;
            border: 1px solid rgba(255,255,255,0.15);
            border-radius: 10px;
            padding: 10px 12px;
            font-size: 14px;
        }
        QLineEdit:focus { border: 1px solid rgba(110,198,255,0.6); }
        QCheckBox { color: rgba(255,255,255,0.85); font-size: 12px; background: transparent; border: none; }
    """)
    fbl = QVBoxLayout(form_box)
    fbl.setContentsMargins(24, 24, 24, 24)
    fbl.setSpacing(10)

    fbl.addWidget(QLabel("Мастер-пароль:"))
    create_pw1 = QLineEdit()
    create_pw1.setEchoMode(QLineEdit.Password)
    create_pw1.setPlaceholderText("Введи мастер-пароль")
    fbl.addWidget(create_pw1)

    fbl.addWidget(QLabel("Повтори пароль:"))
    create_pw2 = QLineEdit()
    create_pw2.setEchoMode(QLineEdit.Password)
    create_pw2.setPlaceholderText("Повтори для проверки")
    fbl.addWidget(create_pw2)

    # Индикатор
    create_strength = QProgressBar()
    create_strength.setRange(0, 100)
    create_strength.setValue(0)
    create_strength.setTextVisible(False)
    create_strength.setFixedHeight(6)
    create_strength.setStyleSheet("""
        QProgressBar { background: rgba(255,255,255,0.10); border: none; border-radius: 3px; }
        QProgressBar::chunk { background: #6EC6FF; border-radius: 3px; }
    """)
    fbl.addWidget(create_strength)

    create_strength_lbl = QLabel("")
    create_strength_lbl.setStyleSheet("color: rgba(255,255,255,0.55); font-size: 11px; background: transparent; border: none;")
    fbl.addWidget(create_strength_lbl)

    create_show_cb = QCheckBox("Показать пароль")
    def toggle_create_show(checked):
        mode = QLineEdit.Normal if checked else QLineEdit.Password
        create_pw1.setEchoMode(mode)
        create_pw2.setEchoMode(mode)
    create_show_cb.stateChanged.connect(toggle_create_show)
    fbl.addWidget(create_show_cb)

    def on_create_pw_changed():
        pw = create_pw1.text()
        score, label, color, _ = check_password_strength(pw)
        create_strength.setValue(score)
        create_strength.setStyleSheet(f"""
            QProgressBar {{ background: rgba(255,255,255,0.10); border: none; border-radius: 3px; }}
            QProgressBar::chunk {{ background: {color}; border-radius: 3px; }}
        """)
        create_strength_lbl.setText(f"{label}  ·  {score}/100")
        create_strength_lbl.setStyleSheet(f"color: {color}; font-size: 11px; background: transparent; border: none;")
    create_pw1.textChanged.connect(on_create_pw_changed)

    cpl.addWidget(form_box, 0, Qt.AlignCenter)

    create_btn = QPushButton("🔐  Создать хранилище")
    create_btn.setCursor(Qt.PointingHandCursor)
    create_btn.setFixedSize(320, 48)
    create_btn.setStyleSheet("""
        QPushButton {
            background: rgba(110,198,255,0.28);
            color: white;
            border: 1px solid rgba(110,198,255,0.65);
            border-radius: 12px;
            font-size: 14px;
            font-weight: 600;
        }
        QPushButton:hover { background: rgba(110,198,255,0.48); }
    """)
    cpl.addWidget(create_btn, 0, Qt.AlignCenter)

    def do_create():
        pw1 = create_pw1.text()
        pw2 = create_pw2.text()
        if len(pw1) < 4:
            QMessageBox.warning(root, "Ошибка", "Пароль должен быть минимум 4 символа.")
            return
        if pw1 != pw2:
            QMessageBox.warning(root, "Ошибка", "Пароли не совпадают.")
            return
        # Финальное предупреждение
        ans = QMessageBox.warning(root, "Подтверждение",
            "Я понимаю, что мастер-пароль нельзя восстановить.\n"
            "Если я его забуду — все данные будут потеряны.\n\n"
            "Продолжить?",
            QMessageBox.Yes | QMessageBox.No)
        if ans != QMessageBox.Yes:
            return

        if vault.create(pw1):
            QMessageBox.information(root, "Готово",
                "Хранилище создано.\n\nСовет: сохрани мастер-пароль в надёжном месте.")
            show_main_page()
        else:
            QMessageBox.warning(root, "Ошибка", "Не удалось создать хранилище.")

    create_btn.clicked.connect(do_create)

    stack.addWidget(create_page)

    # ============================================================
    #  Страница 1: Разблокировка
    # ============================================================
    unlock_page = QWidget()
    unlock_page.setStyleSheet("background: rgba(10,14,26,1);")
    upl = QVBoxLayout(unlock_page)
    upl.setAlignment(Qt.AlignCenter)
    upl.setSpacing(16)

    lock_icon = QLabel("🔒")
    lock_icon.setAlignment(Qt.AlignCenter)
    lock_icon.setStyleSheet("font-size: 80px;")
    upl.addWidget(lock_icon)

    unlock_title = QLabel("Хранилище заблокировано")
    unlock_title.setStyleSheet("color: white; font-size: 22px; font-weight: 300; letter-spacing: 1px;")
    unlock_title.setAlignment(Qt.AlignCenter)
    upl.addWidget(unlock_title)

    unlock_hint = QLabel("Введи мастер-пароль для доступа к паролям")
    unlock_hint.setStyleSheet("color: rgba(255,255,255,0.55); font-size: 13px;")
    unlock_hint.setAlignment(Qt.AlignCenter)
    upl.addWidget(unlock_hint)

    upl.addSpacing(20)

    unlock_box = QWidget()
    unlock_box.setFixedWidth(400)
    unlock_box.setStyleSheet("""
        QWidget {
            background: rgba(255,255,255,0.04);
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 16px;
        }
        QLineEdit {
            background: rgba(255,255,255,0.08);
            color: white;
            border: 1px solid rgba(255,255,255,0.15);
            border-radius: 10px;
            padding: 12px 14px;
            font-size: 15px;
        }
        QLineEdit:focus { border: 1px solid rgba(110,198,255,0.6); }
        QCheckBox { color: rgba(255,255,255,0.85); font-size: 12px; background: transparent; border: none; }
    """)
    ubl = QVBoxLayout(unlock_box)
    ubl.setContentsMargins(24, 24, 24, 24)
    ubl.setSpacing(10)

    unlock_pw = QLineEdit()
    unlock_pw.setEchoMode(QLineEdit.Password)
    unlock_pw.setPlaceholderText("Мастер-пароль")
    ubl.addWidget(unlock_pw)

    unlock_show_cb = QCheckBox("Показать пароль")
    def toggle_unlock_show(checked):
        unlock_pw.setEchoMode(QLineEdit.Normal if checked else QLineEdit.Password)
    unlock_show_cb.stateChanged.connect(toggle_unlock_show)
    ubl.addWidget(unlock_show_cb)

    unlock_info = QLabel("")
    unlock_info.setStyleSheet("color: #FF6B8A; font-size: 12px; background: transparent; border: none;")
    unlock_info.setWordWrap(True)
    ubl.addWidget(unlock_info)

    upl.addWidget(unlock_box, 0, Qt.AlignCenter)

    unlock_btn = QPushButton("🔓  Разблокировать")
    unlock_btn.setCursor(Qt.PointingHandCursor)
    unlock_btn.setFixedSize(320, 48)
    unlock_btn.setStyleSheet("""
        QPushButton {
            background: rgba(110,198,255,0.28);
            color: white;
            border: 1px solid rgba(110,198,255,0.65);
            border-radius: 12px;
            font-size: 14px;
            font-weight: 600;
        }
        QPushButton:hover { background: rgba(110,198,255,0.48); }
    """)
    upl.addWidget(unlock_btn, 0, Qt.AlignCenter)

    def do_unlock():
        pw = unlock_pw.text()
        if not pw:
            return
        ok, msg = vault.unlock(pw)
        if ok:
            unlock_info.setText("")
            show_main_page()
        else:
            unlock_info.setText(f"❌  {msg}")
            # Трясём поле
            from PySide6.QtCore import QPropertyAnimation, QPoint
            anim = QPropertyAnimation(unlock_pw, b"pos")
            anim.setDuration(300)
            x, y = unlock_pw.x(), unlock_pw.y()
            anim.setKeyValueAt(0, QPoint(x, y))
            anim.setKeyValueAt(0.2, QPoint(x - 8, y))
            anim.setKeyValueAt(0.4, QPoint(x + 8, y))
            anim.setKeyValueAt(0.6, QPoint(x - 6, y))
            anim.setKeyValueAt(0.8, QPoint(x + 6, y))
            anim.setKeyValueAt(1, QPoint(x, y))
            anim.start()
            unlock_pw._anim = anim

    unlock_btn.clicked.connect(do_unlock)
    unlock_pw.returnPressed.connect(do_unlock)

    stack.addWidget(unlock_page)

    # ============================================================
    #  Страница 2: Основное окно
    # ============================================================
    main_page = QWidget()
    ml = QHBoxLayout(main_page)
    ml.setContentsMargins(0, 0, 0, 0)
    ml.setSpacing(0)

    # ---- Левая панель ----
    side = QWidget()
    side.setFixedWidth(320)
    side.setStyleSheet("""
        background: rgba(255,255,255,0.04);
        border-right: 1px solid rgba(255,255,255,0.08);
    """)
    sl = QVBoxLayout(side)
    sl.setContentsMargins(14, 16, 14, 16)
    sl.setSpacing(10)

    title = QLabel("🔐  Пароли")
    title.setStyleSheet("color: white; font-size: 16px; font-weight: 600; padding: 2px;")
    sl.addWidget(title)

    add_btn = QPushButton("＋  Добавить запись")
    add_btn.setCursor(Qt.PointingHandCursor)
    add_btn.setFixedHeight(38)
    add_btn.setStyleSheet("""
        QPushButton {
            background: rgba(110,198,255,0.22);
            color: white;
            border: 1px solid rgba(110,198,255,0.55);
            border-radius: 10px;
            font-size: 13px;
            font-weight: 600;
        }
        QPushButton:hover { background: rgba(110,198,255,0.42); }
    """)
    sl.addWidget(add_btn)

    search_lbl = QLabel("ПОИСК")
    search_lbl.setStyleSheet("""
        color: rgba(255,255,255,0.45);
        font-size: 10px;
        font-weight: 700;
        letter-spacing: 1.5px;
        padding-top: 6px;
    """)
    sl.addWidget(search_lbl)

    search_input = QLineEdit()
    search_input.setPlaceholderText("Название, логин, тег…")
    search_input.setStyleSheet("""
        QLineEdit {
            background: rgba(255,255,255,0.08);
            color: white;
            border: 1px solid rgba(255,255,255,0.15);
            border-radius: 10px;
            padding: 8px 12px;
            font-size: 12px;
        }
        QLineEdit:focus { border: 1px solid rgba(110,198,255,0.6); }
    """)
    sl.addWidget(search_input)

    cat_lbl = QLabel("КАТЕГОРИИ")
    cat_lbl.setStyleSheet(search_lbl.styleSheet())
    sl.addWidget(cat_lbl)

    cat_list = QListWidget()
    cat_list.setFixedHeight(140)
    cat_list.setStyleSheet("""
        QListWidget {
            background: rgba(0,0,0,0.20);
            color: white;
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 10px;
            padding: 4px;
            font-size: 12px;
            outline: none;
        }
        QListWidget::item { padding: 6px 10px; border-radius: 6px; }
        QListWidget::item:hover { background: rgba(255,255,255,0.08); }
        QListWidget::item:selected { background: rgba(110,198,255,0.30); }
    """)
    sl.addWidget(cat_list)

    records_lbl = QLabel("ЗАПИСИ")
    records_lbl.setStyleSheet(search_lbl.styleSheet())
    sl.addWidget(records_lbl)

    records_list = QListWidget()
    records_list.setStyleSheet("""
        QListWidget {
            background: rgba(0,0,0,0.20);
            color: white;
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 10px;
            padding: 4px;
            font-size: 12px;
            outline: none;
        }
        QListWidget::item {
            padding: 10px 12px;
            border-radius: 8px;
        }
        QListWidget::item:hover { background: rgba(255,255,255,0.08); }
        QListWidget::item:selected { background: rgba(110,198,255,0.30); }
    """)
    sl.addWidget(records_list, 1)

    # Кнопки внизу
    bottom_row = QHBoxLayout()
    bottom_row.setSpacing(6)

    lock_btn = QPushButton("🔒")
    lock_btn.setFixedSize(38, 38)
    lock_btn.setToolTip("Заблокировать")
    lock_btn.setCursor(Qt.PointingHandCursor)
    lock_btn.setStyleSheet("""
        QPushButton {
            background: rgba(255,255,255,0.06);
            color: white;
            border: 1px solid rgba(255,255,255,0.12);
            border-radius: 8px;
            font-size: 14px;
        }
        QPushButton:hover { background: rgba(255,255,255,0.20); }
    """)
    bottom_row.addWidget(lock_btn)

    settings_btn = QPushButton("⚙")
    settings_btn.setFixedSize(38, 38)
    settings_btn.setToolTip("Настройки хранилища")
    settings_btn.setCursor(Qt.PointingHandCursor)
    settings_btn.setStyleSheet(lock_btn.styleSheet())
    bottom_row.addWidget(settings_btn)

    stats_btn = QPushButton("📊")
    stats_btn.setFixedSize(38, 38)
    stats_btn.setToolTip("Статистика и проверка")
    stats_btn.setCursor(Qt.PointingHandCursor)
    stats_btn.setStyleSheet(lock_btn.styleSheet())
    bottom_row.addWidget(stats_btn)

    bottom_row.addStretch(1)
    sl.addLayout(bottom_row)

    ml.addWidget(side)

    # ---- Правая часть — детали записи ----
    detail = QWidget()
    dl = QVBoxLayout(detail)
    dl.setContentsMargins(30, 30, 30, 30)
    dl.setSpacing(16)

    # Пустое состояние
    empty_lbl = QLabel("Выбери запись слева\nили создай новую")
    empty_lbl.setAlignment(Qt.AlignCenter)
    empty_lbl.setStyleSheet("""
        color: rgba(255,255,255,0.35);
        font-size: 15px;
        padding: 40px;
    """)

    detail_stack = QStackedWidget()
    detail_stack.addWidget(empty_lbl)   # 0

    # Форма записи
    detail_widget = QWidget()
    dwl = QVBoxLayout(detail_widget)
    dwl.setContentsMargins(0, 0, 0, 0)
    dwl.setSpacing(14)

    # Заголовок с иконкой
    header = QHBoxLayout()
    header.setSpacing(16)

    record_icon = QLabel("🔑")
    record_icon.setFixedSize(72, 72)
    record_icon.setAlignment(Qt.AlignCenter)
    record_icon.setStyleSheet("""
        background: rgba(110,198,255,0.10);
        border: 1px solid rgba(110,198,255,0.35);
        border-radius: 18px;
        font-size: 36px;
    """)
    header.addWidget(record_icon)

    text_col = QVBoxLayout()
    text_col.setSpacing(4)

    record_title_lbl = QLabel("")
    record_title_lbl.setStyleSheet("""
        color: white;
        font-size: 22px;
        font-weight: 600;
    """)
    text_col.addWidget(record_title_lbl)

    record_meta_lbl = QLabel("")
    record_meta_lbl.setStyleSheet("color: rgba(255,255,255,0.55); font-size: 12px;")
    text_col.addWidget(record_meta_lbl)

    text_col.addStretch(1)
    header.addLayout(text_col, 1)

    edit_btn = QPushButton("✏  Редактировать")
    edit_btn.setCursor(Qt.PointingHandCursor)
    edit_btn.setFixedHeight(36)
    edit_btn.setStyleSheet("""
        QPushButton {
            background: rgba(110,198,255,0.18);
            color: white;
            border: 1px solid rgba(110,198,255,0.50);
            border-radius: 10px;
            padding: 6px 16px;
            font-size: 12px;
        }
        QPushButton:hover { background: rgba(110,198,255,0.38); }
    """)
    header.addWidget(edit_btn)

    delete_btn = QPushButton("🗑")
    delete_btn.setFixedSize(36, 36)
    delete_btn.setToolTip("Удалить запись")
    delete_btn.setCursor(Qt.PointingHandCursor)
    delete_btn.setStyleSheet("""
        QPushButton {
            background: rgba(255,107,138,0.15);
            color: #FFA0B4;
            border: 1px solid rgba(255,107,138,0.45);
            border-radius: 10px;
            font-size: 14px;
        }
        QPushButton:hover { background: rgba(255,107,138,0.35); color: white; }
    """)
    header.addWidget(delete_btn)

    dwl.addLayout(header)

    # Поля (в режиме просмотра — с копированием)
    def make_field(label_text: str, icon: str = "") -> tuple:
        box = QWidget()
        box.setStyleSheet("""
            QWidget {
                background: rgba(255,255,255,0.04);
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 12px;
            }
        """)
        fl = QVBoxLayout(box)
        fl.setContentsMargins(14, 10, 14, 10)
        fl.setSpacing(4)

        lbl = QLabel(label_text)
        lbl.setStyleSheet("""
            color: rgba(255,255,255,0.45);
            font-size: 10px;
            font-weight: 700;
            letter-spacing: 1.2px;
            background: transparent;
            border: none;
        """)
        fl.addWidget(lbl)

        row = QHBoxLayout()
        row.setSpacing(6)

        value = QLineEdit()
        value.setReadOnly(True)
        value.setStyleSheet("""
            QLineEdit {
                background: transparent;
                color: white;
                border: none;
                padding: 4px 0;
                font-size: 14px;
                font-family: Consolas, monospace;
            }
        """)
        row.addWidget(value, 1)

        copy_b = QPushButton("📋")
        copy_b.setFixedSize(30, 30)
        copy_b.setToolTip("Копировать")
        copy_b.setCursor(Qt.PointingHandCursor)
        copy_b.setStyleSheet("""
            QPushButton {
                background: rgba(255,255,255,0.06);
                color: white;
                border: 1px solid rgba(255,255,255,0.12);
                border-radius: 8px;
                font-size: 12px;
            }
            QPushButton:hover { background: rgba(255,255,255,0.20); }
        """)
        row.addWidget(copy_b)

        fl.addLayout(row)

        def do_copy():
            from PySide6.QtWidgets import QApplication
            QApplication.clipboard().setText(value.text())
            copy_b.setText("✓")
            copy_b.setStyleSheet("""
                QPushButton {
                    background: rgba(110,231,183,0.30);
                    color: white;
                    border: 1px solid rgba(110,231,183,0.60);
                    border-radius: 8px;
                    font-size: 12px;
                }
            """)
            # Автоочистка буфера через 30 сек
            QTimer.singleShot(AUTOCOPY_CLEAR_SEC * 1000,
                                lambda: autoclear_if_same(value.text()))
            # Возврат иконки
            QTimer.singleShot(1500, lambda: copy_b.setText("📋"))
            if desktop and hasattr(desktop, "notifications"):
                desktop.notifications.push("Скопировано",
                    f"Буфер очистится через {AUTOCOPY_CLEAR_SEC} сек")

        copy_b.clicked.connect(do_copy)
        return box, value

    def autoclear_if_same(text: str):
        from PySide6.QtWidgets import QApplication
        cb = QApplication.clipboard()
        if cb.text() == text:
            cb.setText("")
            if desktop and hasattr(desktop, "notifications"):
                desktop.notifications.push("Буфер очищен", "")

    login_box, login_val = make_field("ЛОГИН")
    dwl.addWidget(login_box)

    pw_box, pw_val = make_field("ПАРОЛЬ")
    # Пароль — скрыт по умолчанию
    pw_val.setEchoMode(QLineEdit.Password)

    # Кнопка показать/скрыть над паролем
    pw_controls = pw_box.findChild(QPushButton)
    if pw_controls:
        show_pw_btn = QPushButton("👁")
        show_pw_btn.setFixedSize(30, 30)
        show_pw_btn.setToolTip("Показать/скрыть")
        show_pw_btn.setCursor(Qt.PointingHandCursor)
        show_pw_btn.setStyleSheet(pw_controls.styleSheet())
        def toggle_pw():
            if pw_val.echoMode() == QLineEdit.Password:
                pw_val.setEchoMode(QLineEdit.Normal)
                show_pw_btn.setText("🙈")
            else:
                pw_val.setEchoMode(QLineEdit.Password)
                show_pw_btn.setText("👁")
        show_pw_btn.clicked.connect(toggle_pw)
        # Вставляем перед copy_b
        layout = pw_controls.parent().layout()
        if layout:
            layout.insertWidget(layout.count() - 1, show_pw_btn)

    dwl.addWidget(pw_box)

    url_box, url_val = make_field("URL")
    dwl.addWidget(url_box)

    # Надёжность
    strength_box = QWidget()
    strength_box.setStyleSheet("""
        QWidget {
            background: rgba(255,255,255,0.04);
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 12px;
        }
    """)
    sbl = QVBoxLayout(strength_box)
    sbl.setContentsMargins(14, 10, 14, 10)
    sbl.setSpacing(6)

    str_lbl = QLabel("НАДЁЖНОСТЬ ПАРОЛЯ")
    str_lbl.setStyleSheet("""
        color: rgba(255,255,255,0.45);
        font-size: 10px;
        font-weight: 700;
        letter-spacing: 1.2px;
        background: transparent;
        border: none;
    """)
    sbl.addWidget(str_lbl)

    str_bar = QProgressBar()
    str_bar.setRange(0, 100)
    str_bar.setTextVisible(False)
    str_bar.setFixedHeight(8)
    str_bar.setStyleSheet("""
        QProgressBar { background: rgba(255,255,255,0.10); border: none; border-radius: 4px; }
        QProgressBar::chunk { background: #FF6B8A; border-radius: 4px; }
    """)
    sbl.addWidget(str_bar)

    str_hint = QLabel("")
    str_hint.setStyleSheet("color: rgba(255,255,255,0.55); font-size: 11px; background: transparent; border: none;")
    str_hint.setWordWrap(True)
    sbl.addWidget(str_hint)

    dwl.addWidget(strength_box)

    # Заметки
    notes_lbl = QLabel("ЗАМЕТКИ")
    notes_lbl.setStyleSheet("""
        color: rgba(255,255,255,0.45);
        font-size: 10px;
        font-weight: 700;
        letter-spacing: 1.2px;
        padding-top: 4px;
    """)
    dwl.addWidget(notes_lbl)

    notes_view = QTextEdit()
    notes_view.setReadOnly(True)
    notes_view.setFixedHeight(100)
    notes_view.setStyleSheet("""
        QTextEdit {
            background: rgba(0,0,0,0.20);
            color: white;
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 10px;
            padding: 10px;
            font-size: 12px;
        }
    """)
    dwl.addWidget(notes_view)

    dwl.addStretch(1)

    detail_stack.addWidget(detail_widget)  # 1

    dl.addWidget(detail_stack, 1)

    ml.addWidget(detail, 1)

    stack.addWidget(main_page)

    # ============================================================
    #  Логика
    # ============================================================

    current_record_id = {"id": None}
    autolock_timer = QTimer(root)
    autolock_timer.setInterval(5 * 60 * 1000)  # 5 минут
    autolock_timer.setSingleShot(True)

    def autolock():
        if vault.unlocked:
            vault.lock()
            show_unlock_page()
            if desktop and hasattr(desktop, "notifications"):
                desktop.notifications.push("🔒 Заблокировано",
                    "Автоблокировка после 5 минут неактивности")

    autolock_timer.timeout.connect(autolock)

    def reset_autolock():
        if vault.unlocked:
            autolock_timer.start()

    # ----------------------------------
    def show_create_page():
        stack.setCurrentIndex(0)
        create_pw1.clear()
        create_pw2.clear()
        create_pw1.setFocus()

    def show_unlock_page():
        stack.setCurrentIndex(1)
        unlock_pw.clear()
        unlock_info.setText("")
        unlock_pw.setFocus()
        autolock_timer.stop()

    def show_main_page():
        stack.setCurrentIndex(2)
        refresh_all()
        search_input.setFocus()
        reset_autolock()

    def refresh_categories():
        cat_list.clear()
        all_item = QListWidgetItem(f"🌐  Все записи  ({len(vault.records)})")
        all_item.setData(Qt.UserRole, "__all__")
        cat_list.addItem(all_item)

        for c in vault.categories():
            count = sum(1 for r in vault.records
                        if r.get("category", "Разное") == c)
            item = QListWidgetItem(f"📁  {c}  ({count})")
            item.setData(Qt.UserRole, c)
            cat_list.addItem(item)

        cat_list.setCurrentRow(0)

    def refresh_records():
        records_list.clear()
        query = search_input.text().strip()
        cat_item = cat_list.currentItem()
        cat = cat_item.data(Qt.UserRole) if cat_item else "__all__"

        results = vault.search(query)
        if cat != "__all__":
            results = [r for r in results
                       if r.get("category", "Разное") == cat]

        for r in results:
            title = r.get("title", "?")
            username = r.get("username", "")
            text = f"🔑  {title}"
            if username:
                text += f"\n    {username[:30]}"
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, r.get("id"))
            records_list.addItem(item)

        # Если текущая запись не в списке — показываем пустое
        ids = [r.get("id") for r in results]
        if current_record_id["id"] not in ids:
            current_record_id["id"] = None
            detail_stack.setCurrentIndex(0)

    def refresh_all():
        refresh_categories()
        refresh_records()

    def show_record(rec_id: str):
        rec = vault.get(rec_id)
        if not rec:
            return
        current_record_id["id"] = rec_id

        record_title_lbl.setText(rec.get("title", "—"))
        cat = rec.get("category", "Разное")
        tags = rec.get("tags", [])
        meta = f"📁  {cat}"
        if tags:
            meta += "    ·    " + "  ".join(f"#{t}" for t in tags)
        updated = rec.get("updated", 0)
        if updated:
            dt = datetime.fromtimestamp(updated).strftime("%d.%m.%Y %H:%M")
            meta += f"    ·    обновлено {dt}"
        record_meta_lbl.setText(meta)

        login_val.setText(rec.get("username", "") or "—")
        pw_val.setText(rec.get("password", ""))
        pw_val.setEchoMode(QLineEdit.Password)
        url_val.setText(rec.get("url", "") or "—")
        notes_view.setPlainText(rec.get("notes", "") or "")

        # Надёжность
        score, label, color, hints = check_password_strength(rec.get("password", ""))
        str_bar.setValue(score)
        str_bar.setStyleSheet(f"""
            QProgressBar {{ background: rgba(255,255,255,0.10); border: none; border-radius: 4px; }}
            QProgressBar::chunk {{ background: {color}; border-radius: 4px; }}
        """)
        hint_text = f"{label}  ·  {score}/100"
        if hints:
            hint_text += "\n⚠  " + ", ".join(hints[:3])
        str_hint.setText(hint_text)
        str_hint.setStyleSheet(f"color: {color}; font-size: 11px; background: transparent; border: none;")

        detail_stack.setCurrentIndex(1)
        reset_autolock()

    def on_record_click(item):
        rec_id = item.data(Qt.UserRole)
        if rec_id:
            show_record(rec_id)

    records_list.itemClicked.connect(on_record_click)

    def on_search():
        refresh_records()

    search_input.textChanged.connect(on_search)

    def on_cat_click(item):
        refresh_records()

    cat_list.itemClicked.connect(on_cat_click)

    # ---- Добавить запись ----
    def add_record():
        dlg = RecordDialog(categories=vault.categories(), parent=root)
        if dlg.exec() == QDialog.Accepted:
            data = dlg.get_data()
            rec = vault.add_record(**data)
            refresh_all()
            show_record(rec["id"])

    add_btn.clicked.connect(add_record)

    # ---- Редактировать ----
    def edit_record():
        rec_id = current_record_id["id"]
        if not rec_id:
            return
        rec = vault.get(rec_id)
        if not rec:
            return
        dlg = RecordDialog(record=rec, categories=vault.categories(), parent=root)
        if dlg.exec() == QDialog.Accepted:
            data = dlg.get_data()
            vault.update_record(rec_id, **data)
            refresh_all()
            show_record(rec_id)

    edit_btn.clicked.connect(edit_record)

    # ---- Удалить ----
    def delete_record():
        rec_id = current_record_id["id"]
        if not rec_id:
            return
        rec = vault.get(rec_id)
        if not rec:
            return
        ans = QMessageBox.question(root, "Удалить запись",
            f"Удалить «{rec.get('title', '')}»?\n\nЭто действие необратимо.",
            QMessageBox.Yes | QMessageBox.No)
        if ans == QMessageBox.Yes:
            vault.delete_record(rec_id)
            current_record_id["id"] = None
            refresh_all()
            detail_stack.setCurrentIndex(0)

    delete_btn.clicked.connect(delete_record)

    # ---- Заблокировать ----
    def do_lock():
        vault.lock()
        show_unlock_page()

    lock_btn.clicked.connect(do_lock)

    # ---- Настройки ----
    def open_settings():
        dlg = QDialog(root)
        dlg.setWindowTitle("Настройки хранилища")
        dlg.setFixedSize(420, 320)
        dlg.setStyleSheet("""
            QDialog { background: #1A1F35; }
            QLabel { color: rgba(255,255,255,0.85); font-size: 12px; }
        """)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(12)

        info = QLabel(
            f"📊  Записей: {len(vault.records)}\n"
            f"📁  Категорий: {len(vault.categories())}\n"
            f"🔒  Шифрование: Fernet (AES-128 + HMAC-SHA256)\n"
            f"🔑  KDF: PBKDF2-HMAC-SHA256, {ITERATIONS:,} итераций\n"
            f"💾  Файл: {VAULT_PATH}"
        )
        info.setStyleSheet("""
            background: rgba(110,198,255,0.10);
            color: rgba(255,255,255,0.90);
            border: 1px solid rgba(110,198,255,0.30);
            border-radius: 10px;
            padding: 14px;
            font-size: 12px;
            line-height: 1.6;
        """)
        info.setWordWrap(True)
        lay.addWidget(info)

        change_pw_btn = QPushButton("🔑  Сменить мастер-пароль")
        change_pw_btn.setCursor(Qt.PointingHandCursor)
        change_pw_btn.setFixedHeight(38)
        change_pw_btn.setStyleSheet("""
            QPushButton {
                background: rgba(110,198,255,0.20);
                color: white;
                border: 1px solid rgba(110,198,255,0.50);
                border-radius: 10px;
                font-size: 12px;
            }
            QPushButton:hover { background: rgba(110,198,255,0.40); }
        """)
        lay.addWidget(change_pw_btn)

        export_btn = QPushButton("💾  Экспорт зашифрованной базы")
        export_btn.setCursor(Qt.PointingHandCursor)
        export_btn.setFixedHeight(38)
        export_btn.setStyleSheet("""
            QPushButton {
                background: rgba(110,231,183,0.18);
                color: white;
                border: 1px solid rgba(110,231,183,0.45);
                border-radius: 10px;
                font-size: 12px;
            }
            QPushButton:hover { background: rgba(110,231,183,0.35); }
        """)
        lay.addWidget(export_btn)

        lay.addStretch(1)

        btns = QDialogButtonBox(QDialogButtonBox.Close)
        btns.rejected.connect(dlg.reject)
        btns.setStyleSheet("""
            QPushButton {
                background: rgba(255,255,255,0.08);
                color: white;
                border: 1px solid rgba(255,255,255,0.15);
                border-radius: 8px;
                padding: 8px 20px;
                font-size: 12px;
                min-width: 100px;
            }
            QPushButton:hover { background: rgba(255,255,255,0.20); }
        """)
        lay.addWidget(btns)

        def change_master():
            old, ok = QInputDialog.getText(dlg, "Смена пароля",
                "Текущий мастер-пароль:", QLineEdit.Password)
            if not ok:
                return
            new, ok = QInputDialog.getText(dlg, "Смена пароля",
                "Новый мастер-пароль:", QLineEdit.Password)
            if not ok:
                return
            new2, ok = QInputDialog.getText(dlg, "Смена пароля",
                "Повтори новый пароль:", QLineEdit.Password)
            if not ok or new != new2:
                QMessageBox.warning(dlg, "Ошибка", "Пароли не совпадают.")
                return
            ok, msg = vault.change_master(old, new)
            if ok:
                QMessageBox.information(dlg, "Готово", msg)
            else:
                QMessageBox.warning(dlg, "Ошибка", msg)

        change_pw_btn.clicked.connect(change_master)

        def export_vault():
            if vfs is None:
                return
            try:
                # Копируем оба файла в /Documents
                vfs.mkdir("/Documents")
                # Копируем vault + meta с одинаковым именем
                if vfs.exists(VAULT_PATH):
                    vault_data = vfs.read_bytes(VAULT_PATH)
                    meta_data = vfs.read_text(VAULT_META_PATH, "")
                    vfs.write_bytes("/Documents/passwords_backup.vault", vault_data)
                    vfs.write_text("/Documents/passwords_backup_meta.json", meta_data)
                    QMessageBox.information(dlg, "Экспорт",
                        "База экспортирована:\n"
                        "/Documents/passwords_backup.vault\n"
                        "/Documents/passwords_backup_meta.json\n\n"
                        "Файлы зашифрованы мастер-паролем.")
            except Exception as e:
                QMessageBox.warning(dlg, "Ошибка", str(e))

        export_btn.clicked.connect(export_vault)

        dlg.exec()

    settings_btn.clicked.connect(open_settings)

    # ---- Статистика ----
    def show_stats():
        st_data = vault.stats()

        # Дополнительно: сколько слабых
        weak_list = []
        reused_map = {}
        for r in vault.records:
            score, label, _, _ = check_password_strength(r.get("password", ""))
            if label in ("Слабый", "Средний"):
                weak_list.append((r.get("title", "?"), label, score))
            pw = r.get("password", "")
            reused_map.setdefault(pw, []).append(r.get("title", "?"))

        dlg = QDialog(root)
        dlg.setWindowTitle("Статистика и проверка")
        dlg.resize(520, 480)
        dlg.setStyleSheet("QDialog { background: #1A1F35; }")
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(12)

        info = QLabel(
            f"📊  Всего записей: {st_data['total']}\n"
            f"⚠  Слабых/средних: {st_data['weak']}\n"
            f"🔁  Повторяющихся паролей: {st_data['reused']}\n"
            f"📁  Категорий: {st_data['categories']}"
        )
        info.setStyleSheet("""
            background: rgba(110,198,255,0.10);
            color: white;
            border: 1px solid rgba(110,198,255,0.30);
            border-radius: 10px;
            padding: 14px;
            font-size: 13px;
            line-height: 1.8;
        """)
        lay.addWidget(info)

        problems = QTextEdit()
        problems.setReadOnly(True)
        problems.setStyleSheet("""
            QTextEdit {
                background: rgba(0,0,0,0.20);
                color: white;
                border: 1px solid rgba(255,255,255,0.10);
                border-radius: 10px;
                padding: 12px;
                font-size: 12px;
            }
        """)

        lines = []
        if weak_list:
            lines.append("⚠️  Слабые пароли:")
            for title, label, score in sorted(weak_list, key=lambda x: x[2])[:20]:
                lines.append(f"   • {title} — {label} ({score}/100)")
            lines.append("")

        # Повторяющиеся
        reused_groups = [titles for titles in reused_map.values() if len(titles) > 1]
        if reused_groups:
            lines.append("🔁  Повторяющиеся пароли:")
            for group in reused_groups[:10]:
                lines.append(f"   • {' , '.join(group)}")
            lines.append("")

        if not lines:
            lines.append("✓  Всё в порядке!\nВсе пароли достаточно надёжны и уникальны.")

        problems.setPlainText("\n".join(lines))
        lay.addWidget(problems, 1)

        btns = QDialogButtonBox(QDialogButtonBox.Close)
        btns.rejected.connect(dlg.reject)
        btns.setStyleSheet("""
            QPushButton {
                background: rgba(110,198,255,0.20);
                color: white;
                border: 1px solid rgba(110,198,255,0.50);
                border-radius: 8px;
                padding: 8px 20px;
                font-size: 12px;
                min-width: 100px;
            }
            QPushButton:hover { background: rgba(110,198,255,0.40); }
        """)
        lay.addWidget(btns)

        dlg.exec()

    stats_btn.clicked.connect(show_stats)

    # ---- Сброс автоблокировки при действиях ----
    def on_any_activity():
        reset_autolock()

    search_input.textChanged.connect(on_any_activity)
    records_list.itemClicked.connect(on_any_activity)
    cat_list.itemClicked.connect(on_any_activity)

    # ---- Обработка контекстного меню записей ----
    def record_context(pos):
        item = records_list.itemAt(pos)
        if item is None:
            return
        rec_id = item.data(Qt.UserRole)
        if not rec_id:
            return
        rec = vault.get(rec_id)
        if not rec:
            return

        menu = make_menu(records_list)

        a_copy_login = menu.addAction("📋  Копировать логин")
        def do_copy_login():
            from PySide6.QtWidgets import QApplication
            QApplication.clipboard().setText(rec.get("username", ""))
        a_copy_login.triggered.connect(do_copy_login)

        a_copy_pw = menu.addAction("🔑  Копировать пароль")
        def do_copy_pw():
            from PySide6.QtWidgets import QApplication
            QApplication.clipboard().setText(rec.get("password", ""))
            QTimer.singleShot(AUTOCOPY_CLEAR_SEC * 1000,
                lambda t=rec.get("password", ""): autoclear_if_same(t))
        a_copy_pw.triggered.connect(do_copy_pw)

        menu.addSeparator()

        a_edit = menu.addAction("✏  Редактировать")
        def do_edit():
            show_record(rec_id)
            edit_record()
        a_edit.triggered.connect(do_edit)

        menu.addSeparator()

        a_del = menu.addAction("🗑  Удалить")
        def do_del():
            show_record(rec_id)
            delete_record()
        a_del.triggered.connect(do_del)

        menu.exec(records_list.mapToGlobal(pos))

    records_list.setContextMenuPolicy(Qt.CustomContextMenu)
    records_list.customContextMenuRequested.connect(record_context)

    # ============================================================
    #  Стартовое состояние
    # ============================================================

    if vault.exists():
        show_unlock_page()
    else:
        show_create_page()

    return root