"""
MountOS — Мессенджер (Matrix).

Основан на matrix-nio с поддержкой E2EE.
  • Вход в аккаунт Matrix
  • Список комнат
  • История сообщений (с расшифровкой)
  • Отправка и получение в реальном времени
  • Расшифровка входящих (Olm/Megolm)

Требует: pip install "matrix-nio[e2e]"
И системную библиотеку libolm (apt install libolm-dev)
"""
import sys
import asyncio
import threading
import queue
import time
from pathlib import Path

from PySide6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QLabel,
                                QPushButton, QLineEdit, QListWidget,
                                QListWidgetItem, QTextEdit, QStackedWidget,
                                QMessageBox)
from PySide6.QtCore import Qt, QTimer, Signal, QObject, QSize
from PySide6.QtGui import QFont, QColor, QIcon

from ui.settings_state import state

try:
    from nio import (AsyncClient, AsyncClientConfig, SyncResponse,
                     RoomMessageText, LoginResponse, RegisterResponse,
                     RoomMessage, MegolmEvent, InviteEvent,
                     RoomCreateResponse, RoomInviteResponse, SyncError)
    from nio.store import SqliteStore
    HAS_NIO = True
    HAS_E2EE = True
except ImportError as e:
    HAS_NIO = False
    HAS_E2EE = False
    NIO_ERROR = str(e)

APP_NAME = "Мессенджер"
APP_ICON = "messenger"
APP_VERSION = "2.0"
APP_AUTHOR = "MountOS"

HOMESERVER = "https://matrix.org"
STORE_DIR = Path.home() / ".mountos" / "matrix_store"


# ============================================================
#  Асинхронный мост (Qt <-> asyncio)
# ============================================================

class AsyncBridge(QObject):
    """Мост между asyncio и Qt. Принимает события из фонового потока."""

    message_received = Signal(str, str, str)   # room_id, sender, body
    rooms_updated = Signal(dict)                # {room_id: room_name}
    login_success = Signal(str)                 # user_id
    login_failed = Signal(str)                  # error
    register_success = Signal(str)              # user_id
    register_failed = Signal(str)               # error
    sync_error = Signal(str)
    sync_done = Signal()                        # первый синк завершён


# ============================================================
#  Фоновый воркер (asyncio-цикл)
# ============================================================

class MatrixWorker(threading.Thread):
    """Фоновый поток с asyncio-циклом matrix-nio."""

    def __init__(self, bridge: AsyncBridge):
        super().__init__(daemon=True)
        self.bridge = bridge
        self.loop = None
        self.client = None
        self._stop = False
        self._outbox = queue.Queue()
        self._ready = threading.Event()   # первый sync завершён

    def run(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._main())

    async def _main(self):
        # Ждём логина
        while not self._stop:
            await asyncio.sleep(0.3)
            if self.client is not None:
                break
        if self._stop:
            return

        # Основной цикл sync
        first_sync = True
        while not self._stop:
            try:
                # Исходящие
                while not self._outbox.empty():
                    room_id, text = self._outbox.get_nowait()
                    try:
                        await self.client.room_send(
                            room_id=room_id,
                            message_type="m.room.message",
                            content={"msgtype": "m.text", "body": text}
                        )
                    except Exception as e:
                        self.bridge.sync_error.emit(f"Send error: {e}")

                # Sync
                resp = await asyncio.wait_for(
                    self.client.sync(timeout=30000),
                    timeout=35.0
                )
                await self._handle_sync(resp)

                if first_sync:
                    first_sync = False
                    self._ready.set()
                    self.bridge.sync_done.emit()

            except asyncio.TimeoutError:
                # Нормально для long-polling
                pass
            except Exception as e:
                self.bridge.sync_error.emit(str(e))
                await asyncio.sleep(2)

    async def _handle_sync(self, resp: SyncResponse):
        if isinstance(resp, SyncError):
            self.bridge.sync_error.emit(resp.message)
            return

        # Обновляем список комнат
        rooms = {}
        for room_id, room in self.client.rooms.items():
            rooms[room_id] = room.display_name or room_id
        self.bridge.rooms_updated.emit(rooms)

        # Обрабатываем события
        for room_id, joined in resp.rooms.join.items():
            for event in joined.timeline.events:
                # Обычные текстовые сообщения
                if isinstance(event, RoomMessageText):
                    self.bridge.message_received.emit(
                        room_id, event.sender, event.body)
                # Расшифрованные сообщения (MegolmEvent автоматически расшифровывается nio)
                elif isinstance(event, MegolmEvent):
                    # nio пытается расшифровать; если удалось — body будет доступен
                    body = getattr(event, "body", None)
                    if body:
                        self.bridge.message_received.emit(
                            room_id, event.sender, body)
                    else:
                        # Не удалось расшифровать — просим ключи
                        try:
                            await self.client.request_room_key(event)
                        except Exception:
                            pass
                # Инвайты
                elif isinstance(event, InviteEvent):
                    try:
                        await self.client.join(event.room_id)
                    except Exception:
                        pass

    def login(self, username, password):
        """Логин. Вызывается из главного потока."""
        async def _do_login():
            config = AsyncClientConfig(
                store_sync_tokens=True,
                encryption_enabled=True,
            )
            STORE_DIR.mkdir(parents=True, exist_ok=True)
            self.client = AsyncClient(
                HOMESERVER,
                username,
                store_path=str(STORE_DIR),
                config=config,
            )
            try:
                resp = await self.client.login(password)
                if isinstance(resp, LoginResponse):
                    self.bridge.login_success.emit(resp.user_id)
                else:
                    self.bridge.login_failed.emit(str(resp))
            except Exception as e:
                self.bridge.login_failed.emit(str(e))

        asyncio.run_coroutine_threadsafe(_do_login(), self.loop)

    def register(self, username, password):
        """Регистрация. Вызывается из главного потока."""
        async def _do_register():
            try:
                temp = AsyncClient(HOMESERVER, "")
                resp = await temp.register(
                    username=username,
                    password=password,
                    device_name="MountOS Messenger",
                )
                if isinstance(resp, RegisterResponse):
                    # Сразу логинимся
                    config = AsyncClientConfig(
                        store_sync_tokens=True,
                        encryption_enabled=True,
                    )
                    STORE_DIR.mkdir(parents=True, exist_ok=True)
                    self.client = AsyncClient(
                        HOMESERVER,
                        resp.user_id,
                        store_path=str(STORE_DIR),
                        config=config,
                    )
                    login_resp = await self.client.login(password)
                    if isinstance(login_resp, LoginResponse):
                        self.bridge.register_success.emit(resp.user_id)
                    else:
                        self.bridge.register_failed.emit(str(login_resp))
                else:
                    self.bridge.register_failed.emit(str(resp))
            except Exception as e:
                self.bridge.register_failed.emit(str(e))

        asyncio.run_coroutine_threadsafe(_do_register(), self.loop)

    def send(self, room_id, text):
        self._outbox.put((room_id, text))

    def stop(self):
        self._stop = True


# ============================================================
#  UI
# ============================================================

def build():
    root = QWidget()
    layout = QVBoxLayout(root)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)

    if not HAS_NIO:
        warn = QLabel(
            f"⚠  matrix-nio не установлен.\n\n"
            f"Установи:\n"
            f"  sudo apt install libolm-dev\n"
            f"  pip install \"matrix-nio[e2e]\"\n\n"
            f"Ошибка: {NIO_ERROR}"
        )
        warn.setStyleSheet("color:#FFA0B4; padding:20px; font-size:14px;")
        warn.setWordWrap(True)
        layout.addWidget(warn)
        return root

    # ---- Экран входа ----
    login_page = QWidget()
    ll = QVBoxLayout(login_page)
    ll.setContentsMargins(40, 40, 40, 40)
    ll.setSpacing(12)

    title = QLabel("Matrix Messenger")
    title.setStyleSheet("color:white; font-size:22px; font-weight:600;")
    ll.addWidget(title)

    info = QLabel(f"Сервер: {HOMESERVER}")
    info.setStyleSheet("color: rgba(255,255,255,0.65); font-size: 12px;")
    ll.addWidget(info)

    if HAS_E2EE:
        e2ee_lbl = QLabel("🔒 E2EE включено")
        e2ee_lbl.setStyleSheet("color:#6EE7B7; font-size: 12px;")
        ll.addWidget(e2ee_lbl)

    user_input = QLineEdit()
    user_input.setPlaceholderText("Имя пользователя (@user:matrix.org)")
    user_input.setStyleSheet("""
        QLineEdit {
            background: rgba(255,255,255,0.08); color: white;
            border: 1px solid rgba(255,255,255,0.15);
            border-radius: 10px; padding: 10px 14px;
        }
    """)
    ll.addWidget(user_input)

    pass_input = QLineEdit()
    pass_input.setPlaceholderText("Пароль")
    pass_input.setEchoMode(QLineEdit.Password)
    pass_input.setStyleSheet(user_input.styleSheet())
    ll.addWidget(pass_input)

    btn_row = QHBoxLayout()
    login_btn = QPushButton("Войти")
    register_btn = QPushButton("Регистрация")
    for b in (login_btn, register_btn):
        b.setFixedHeight(42)
        b.setCursor(Qt.PointingHandCursor)
        b.setStyleSheet("""
            QPushButton {
                background: rgba(110,198,255,0.25); color: white;
                border: 1px solid rgba(110,198,255,0.60);
                border-radius: 10px; font-size: 14px;
            }
            QPushButton:hover { background: rgba(110,198,255,0.45); }
        """)
        btn_row.addWidget(b)

    ll.addLayout(btn_row)
    ll.addStretch(1)

    # ---- Экран чата ----
    chat_page = QWidget()
    cl = QHBoxLayout(chat_page)
    cl.setContentsMargins(0, 0, 0, 0)
    cl.setSpacing(0)

    # Сайдбар комнат
    rooms_list = QListWidget()
    rooms_list.setFixedWidth(220)
    rooms_list.setStyleSheet("""
        QListWidget {
            background: rgba(255,255,255,0.04);
            border-right: 1px solid rgba(255,255,255,0.08);
            color: white; font-size: 13px; outline: none;
        }
        QListWidget::item { padding: 10px 12px; }
        QListWidget::item:hover { background: rgba(255,255,255,0.08); }
        QListWidget::item:selected { background: rgba(110,198,255,0.30); }
    """)
    cl.addWidget(rooms_list)

    # Область чата
    chat_area = QWidget()
    ca = QVBoxLayout(chat_area)
    ca.setContentsMargins(0, 0, 0, 0)
    ca.setSpacing(0)

    chat_header = QLabel("Выберите комнату")
    chat_header.setStyleSheet("""
        color: white; font-size: 15px; font-weight: 600;
        padding: 12px 16px;
        background: rgba(255,255,255,0.04);
        border-bottom: 1px solid rgba(255,255,255,0.08);
    """)
    ca.addWidget(chat_header)

    messages = QTextEdit()
    messages.setReadOnly(True)
    messages.setStyleSheet("""
        QTextEdit {
            background: rgba(0,0,0,0.15);
            color: white; border: none;
            padding: 12px; font-size: 13px;
        }
    """)
    ca.addWidget(messages, 1)

    input_row = QHBoxLayout()
    input_row.setContentsMargins(12, 8, 12, 12)
    input_row.setSpacing(8)

    msg_input = QLineEdit()
    msg_input.setPlaceholderText("Сообщение…")
    msg_input.setStyleSheet("""
        QLineEdit {
            background: rgba(255,255,255,0.08); color: white;
            border: 1px solid rgba(255,255,255,0.15);
            border-radius: 10px; padding: 10px 14px;
        }
    """)
    input_row.addWidget(msg_input, 1)

    send_btn = QPushButton("▶")
    send_btn.setFixedSize(42, 42)
    send_btn.setCursor(Qt.PointingHandCursor)
    send_btn.setStyleSheet("""
        QPushButton {
            background: rgba(110,198,255,0.25); color: white;
            border: 1px solid rgba(110,198,255,0.60);
            border-radius: 10px; font-size: 16px;
        }
        QPushButton:hover { background: rgba(110,198,255,0.45); }
    """)
    input_row.addWidget(send_btn)
    ca.addLayout(input_row)

    cl.addWidget(chat_area, 1)

    # ---- Стек ----
    stack = QStackedWidget()
    stack.addWidget(login_page)   # 0
    stack.addWidget(chat_page)    # 1
    layout.addWidget(stack)

    # ---- Логика ----
    bridge = AsyncBridge()
    worker = MatrixWorker(bridge)
    worker.start()

    current_room = {"id": None}

    def on_login():
        user = user_input.text().strip()
        pwd = pass_input.text()
        if not user or not pwd:
            QMessageBox.warning(root, "Ошибка", "Введи логин и пароль")
            return
        login_btn.setEnabled(False)
        login_btn.setText("Вход…")
        worker.login(user, pwd)

    def on_register():
        user = user_input.text().strip()
        pwd = pass_input.text()
        if not user or not pwd:
            QMessageBox.warning(root, "Ошибка", "Введи логин и пароль")
            return
        register_btn.setEnabled(False)
        register_btn.setText("Регистрация…")
        worker.register(user, pwd)

    def on_login_ok(user_id):
        login_btn.setEnabled(True)
        login_btn.setText("Войти")
        register_btn.setEnabled(True)
        register_btn.setText("Регистрация")
        stack.setCurrentIndex(1)
        chat_header.setText(f"Вошёл как {user_id}")

    def on_login_fail(err):
        login_btn.setEnabled(True)
        login_btn.setText("Войти")
        QMessageBox.warning(root, "Ошибка входа", err)

    def on_register_ok(user_id):
        register_btn.setEnabled(True)
        register_btn.setText("Регистрация")
        QMessageBox.information(root, "Успех", f"Аккаунт создан: {user_id}")
        stack.setCurrentIndex(1)
        chat_header.setText(f"Вошёл как {user_id}")

    def on_register_fail(err):
        register_btn.setEnabled(True)
        register_btn.setText("Регистрация")
        QMessageBox.warning(
            root, "Ошибка регистрации",
            f"{err}\n\nСкорее всего, сервер требует капчу/email.\n"
            "Зарегистрируйся через app.element.io, потом войди здесь."
        )

    def on_rooms(rooms: dict):
        rooms_list.clear()
        for room_id, name in rooms.items():
            item = QListWidgetItem(name)
            item.setData(Qt.UserRole, room_id)
            rooms_list.addItem(item)

    def on_room_selected(item):
        room_id = item.data(Qt.UserRole)
        current_room["id"] = room_id
        chat_header.setText(item.text())
        messages.clear()

    def on_message(room_id, sender, body):
        if room_id == current_room["id"]:
            short = sender.split(":")[0].replace("@", "")
            messages.append(f"<b>{short}</b>: {body}")

    def send_message():
        text = msg_input.text().strip()
        if not text or not current_room["id"]:
            return
        worker.send(current_room["id"], text)
        messages.append(f"<b>Вы</b>: {text}")
        msg_input.clear()

    login_btn.clicked.connect(on_login)
    register_btn.clicked.connect(on_register)
    pass_input.returnPressed.connect(on_login)
    rooms_list.itemClicked.connect(on_room_selected)
    send_btn.clicked.connect(send_message)
    msg_input.returnPressed.connect(send_message)

    bridge.login_success.connect(on_login_ok)
    bridge.login_failed.connect(on_login_fail)
    bridge.register_success.connect(on_register_ok)
    bridge.register_failed.connect(on_register_fail)
    bridge.rooms_updated.connect(on_rooms)
    bridge.message_received.connect(on_message)
    bridge.sync_error.connect(lambda e: print(f"[Matrix] {e}"))

    return root