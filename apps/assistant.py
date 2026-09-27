"""
MountOS — Mount Assistant.

Голосовой помощник на sounddevice (без pyaudio):
  • Распознавание речи через Google Speech Recognition
  • Синтез речи через pyttsx3 (офлайн)
  • Запись с микрофона через sounddevice
  • Управление MountOS голосом

Установка:
    pip install SpeechRecognition pyttsx3 sounddevice numpy
"""

import io
import json
import os
import re
import subprocess
import sys
import threading
import time
import wave
from datetime import datetime

import numpy as np

from PySide6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QLabel,
                                QPushButton, QListWidget, QListWidgetItem,
                                QFrame, QMessageBox, QLineEdit, QSizePolicy)
from PySide6.QtCore import Qt, QTimer, QThread, Signal, QSize
from PySide6.QtGui import QFont, QIcon, QColor, QPainter, QPen, QBrush

from ui.icons import get_icon
from ui.settings_state import state

APP_NAME = "Ассистент"
APP_ICON = "mic"
APP_VERSION = "1.0"
APP_AUTHOR = "MountOS"


HISTORY_PATH = "/Documents/assistant_history.json"
MAX_HISTORY = 100

# Параметры записи
SAMPLE_RATE = 16000
CHANNELS = 1
DTYPE = "int16"
CHUNK = 1024


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
#  Синтез речи
# ============================================================

class Speaker(QThread):
    """Произносит текст через pyttsx3 в фоне."""

    def __init__(self, text: str):
        super().__init__()
        self.text = text

    def run(self):
        try:
            import pyttsx3
            engine = pyttsx3.init()
            engine.setProperty('rate', 180)
            engine.setProperty('volume', 1.0)
            try:
                voices = engine.getProperty('voices')
                for v in voices:
                    if 'ru' in v.id.lower() or 'russian' in v.name.lower():
                        engine.setProperty('voice', v.id)
                        break
            except Exception:
                pass
            engine.say(self.text)
            engine.runAndWait()
        except ImportError:
            print("[Assistant] pyttsx3 не установлен")
        except Exception as e:
            print(f"[Assistant] speak error: {e}")


# ============================================================
#  Распознавание речи через sounddevice
# ============================================================

class Listener(QThread):
    """Слушает микрофон через sounddevice и распознаёт."""

    recognized = Signal(str)
    error = Signal(str)
    status = Signal(str)

    def __init__(self, language: str = "ru-RU", duration: int = 5):
        super().__init__()
        self.language = language
        self.duration = duration

    def run(self):
        try:
            import sounddevice as sd
        except ImportError:
            self.error.emit(
                "Библиотека sounddevice не установлена.\n"
                "Установи: pip install sounddevice numpy")
            return

        try:
            import speech_recognition as sr
        except ImportError:
            self.error.emit(
                "Библиотека SpeechRecognition не установлена.\n"
                "Установи: pip install SpeechRecognition")
            return

        try:
            # Проверяем, есть ли микрофон
            devices = sd.query_devices()
            input_devices = [d for d in devices
                             if d.get("max_input_channels", 0) > 0]
            if not input_devices:
                self.error.emit("Микрофон не найден")
                return

            # Запись
            self.status.emit(f"🎤 Слушаю {self.duration} сек…")

            recording = sd.rec(
                int(self.duration * SAMPLE_RATE),
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype=DTYPE)
            sd.wait()

            self.status.emit("🧠 Распознаю…")

            # Преобразуем numpy → WAV в память
            audio_data = recording.tobytes()
            wav_bytes = self._numpy_to_wav(audio_data)

            # Через speech_recognition
            r = sr.Recognizer()
            audio = sr.AudioData(wav_bytes, SAMPLE_RATE, 2)

            try:
                text = r.recognize_google(audio, language=self.language)
                self.recognized.emit(text)
            except sr.UnknownValueError:
                self.error.emit("Не разобрал речь. Повтори чётче.")
            except sr.RequestError as e:
                self.error.emit(f"Ошибка Google API: {e}\nПроверь интернет.")

        except Exception as e:
            import traceback
            traceback.print_exc()
            self.error.emit(f"Ошибка: {e}")

    def _numpy_to_wav(self, pcm_bytes: bytes) -> bytes:
        """Оборачивает сырые PCM-данные в WAV-контейнер."""
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(pcm_bytes)
        return buf.getvalue()


# ============================================================
#  Обработчик команд
# ============================================================

class CommandProcessor:
    def __init__(self, desktop):
        self.desktop = desktop

    def process(self, text: str) -> str:
        t = text.lower().strip()

        # Приветствия
        if any(w in t for w in ["привет", "здравствуй", "хай", "hello"]):
            hour = datetime.now().hour
            if 5 <= hour < 12:
                return "Доброе утро!"
            elif 12 <= hour < 18:
                return "Добрый день!"
            elif 18 <= hour < 23:
                return "Добрый вечер!"
            return "Доброй ночи!"

        # Открытие приложения
        m = re.search(r"(открой|запусти|запусти-ка)\s+(.+)", t)
        if m:
            return self._open_app(m.group(2).strip())

        # Закрытие окон
        if any(w in t for w in ["закрой все окна", "закрыть всё", "закрой всё"]):
            if self.desktop:
                count = len(self.desktop.windows)
                for w in list(self.desktop.windows):
                    try:
                        w.close()
                    except Exception:
                        pass
                return f"Закрыто окон: {count}"
            return "Не могу закрыть окна"

        # Время
        if any(w in t for w in ["который час", "сколько времени", "время сейчас"]):
            return f"Сейчас {datetime.now().strftime('%H:%M')}"

        # Дата
        if any(w in t for w in ["какое сегодня число", "какая дата", "какое число"]):
            months = ["января", "февраля", "марта", "апреля", "мая", "июня",
                      "июля", "августа", "сентября", "октября", "ноября", "декабря"]
            d = datetime.now()
            return f"Сегодня {d.day} {months[d.month-1]} {d.year} года"

        # Погода
        if "погод" in t:
            if self.desktop:
                self.desktop.open_app("weather")
                return "Открываю погоду"

        # Курсы валют
        if "курс" in t or "валют" in t:
            if self.desktop:
                self.desktop.open_app("currency")
                return "Открываю курсы валют"

        # Поиск
        m = re.search(r"(найди|поиск|ищи)\s+(.+)", t)
        if m:
            query = m.group(2).strip()
            if self.desktop and hasattr(self.desktop, "spotlight"):
                self.desktop.spotlight.toggle()
                self.desktop.spotlight.search.setText(query)
                self.desktop.spotlight._update_results(query)
            return f"Ищу {query}"

        # Заметка
        m = re.search(r"напиши заметку\s+(.+)", t)
        if m:
            note_text = m.group(1)
            vfs = _get_vfs(self.desktop) if self.desktop else None
            if vfs:
                vfs.mkdir("/Notes")
                path = f"/Notes/voice_note_{int(time.time())}.txt"
                vfs.write_text(path, note_text)
                return "Заметка сохранена"
            return "Не могу сохранить"

        # Терминал
        if "терминал" in t:
            if self.desktop:
                self.desktop.open_app("terminal")
                return "Открываю терминал"

        # Блокировка
        if "заблокируй" in t or "блокировка" in t:
            if sys.platform.startswith("win"):
                try:
                    subprocess.run(
                        ["rundll32.exe", "user32.dll,LockWorkStation"],
                        creationflags=subprocess.CREATE_NO_WINDOW
                        if hasattr(subprocess, "CREATE_NO_WINDOW") else 0)
                    return "Экран заблокирован"
                except Exception:
                    pass
            return "Не поддерживается"

        # Спасибо
        if any(w in t for w in ["спасибо", "благодарю"]):
            return "Всегда пожалуйста!"

        # Не понял
        return f"Не знаю, как выполнить «{text}»"

    def _open_app(self, target: str) -> str:
        if not self.desktop or not hasattr(self.desktop, "registry"):
            return "Реестр приложений недоступен"

        target_low = target.lower()
        best = None
        best_score = 0

        for app_id, info in self.desktop.registry.apps.items():
            name_low = info.name.lower()
            app_low = app_id.lower()

            if target_low == name_low or target_low == app_low:
                best = app_id
                break

            if target_low in name_low or name_low in target_low:
                score = min(len(target_low), len(name_low)) / max(len(target_low), len(name_low))
                if score > best_score:
                    best = app_id
                    best_score = score

            if target_low in app_low:
                score = len(target_low) / len(app_low)
                if score > best_score:
                    best = app_id
                    best_score = score

        if best:
            self.desktop.open_app(best)
            return f"Открываю {self.desktop.registry.apps[best].name}"

        return f"Не нашёл приложение {target}"


# ============================================================
#  Индикатор записи (пульсирующий круг)
# ============================================================

class PulseButton(QPushButton):
    """Кнопка с пульсацией во время записи."""

    def __init__(self, parent=None):
        super().__init__("🎤", parent)
        self.setFixedSize(180, 180)
        self.setCursor(Qt.PointingHandCursor)
        self._recording = False
        self._pulse = 0.0

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.setInterval(50)

        self._apply_style()

    def set_recording(self, on: bool):
        self._recording = on
        if on:
            self._timer.start()
        else:
            self._timer.stop()
            self._pulse = 0.0
            self.update()
        self._apply_style()

    def _tick(self):
        self._pulse = (self._pulse + 0.1) % 1.0
        self.update()

    def paintEvent(self, event):
        if self._recording:
            # Пульсация
            p = QPainter(self)
            p.setRenderHint(QPainter.Antialiasing)

            import math
            radius = 90
            pulse_radius = radius + 10 + int(math.sin(self._pulse * math.pi * 2) * 15)

            p.setBrush(QBrush(QColor(255, 107, 138, 60)))
            p.setPen(Qt.NoPen)
            p.drawEllipse(self.rect().center(),
                          pulse_radius, pulse_radius)
        super().paintEvent(event)

    def _apply_style(self):
        if self._recording:
            self.setStyleSheet("""
                QPushButton {
                    background: qradialgradient(cx:0.5, cy:0.5,
                        stop:0 rgba(255,107,138,0.55),
                        stop:1 rgba(255,107,138,0.30));
                    color: white;
                    border: 2px solid rgba(255,107,138,0.95);
                    border-radius: 90px;
                    font-size: 72px;
                }
                QPushButton:hover {
                    background: qradialgradient(cx:0.5, cy:0.5,
                        stop:0 rgba(255,107,138,0.75),
                        stop:1 rgba(255,107,138,0.45));
                }
            """)
        else:
            self.setStyleSheet("""
                QPushButton {
                    background: qradialgradient(cx:0.5, cy:0.5,
                        stop:0 rgba(110,198,255,0.35),
                        stop:1 rgba(110,198,255,0.15));
                    color: white;
                    border: 2px solid rgba(110,198,255,0.65);
                    border-radius: 90px;
                    font-size: 72px;
                }
                QPushButton:hover {
                    background: qradialgradient(cx:0.5, cy:0.5,
                        stop:0 rgba(110,198,255,0.55),
                        stop:1 rgba(110,198,255,0.25));
                    border: 2px solid rgba(110,198,255,0.95);
                }
                QPushButton:pressed {
                    background: rgba(110,198,255,0.75);
                }
                QPushButton:disabled {
                    background: rgba(255,255,255,0.05);
                    color: rgba(255,255,255,0.30);
                    border: 2px solid rgba(255,255,255,0.10);
                }
            """)


# ============================================================
#  Основное приложение
# ============================================================

def build():
    root = QWidget()
    h = QHBoxLayout(root)
    h.setContentsMargins(0, 0, 0, 0)
    h.setSpacing(0)

    vfs = _get_vfs(root)
    desktop = _get_desktop(root)
    processor = CommandProcessor(desktop)

    st = {
        "history": [],
        "listener": None,
        "speaker": None,
        "listening": False,
    }

    # Загружаем историю
    if vfs:
        try:
            raw = vfs.read_text(HISTORY_PATH, "")
            if raw.strip():
                st["history"] = json.loads(raw)
        except Exception:
            st["history"] = []

    def save_history():
        if vfs is None:
            return
        try:
            vfs.mkdir("/Documents")
            vfs.write_text(HISTORY_PATH,
                json.dumps(st["history"][-MAX_HISTORY:],
                            ensure_ascii=False, indent=2))
        except Exception as e:
            print(f"[Assistant] save: {e}")

    # ============================================================
    #  Левая панель
    # ============================================================
    left = QWidget()
    ll = QVBoxLayout(left)
    ll.setContentsMargins(40, 40, 40, 40)
    ll.setSpacing(20)
    ll.setAlignment(Qt.AlignCenter)

    title = QLabel("🎤  Mount Assistant")
    title.setStyleSheet("""
        color: white;
        font-size: 26px;
        font-weight: 300;
        letter-spacing: 1px;
    """)
    title.setAlignment(Qt.AlignCenter)
    ll.addWidget(title)

    subtitle = QLabel("Голосовой помощник MountOS")
    subtitle.setStyleSheet("""
        color: rgba(255,255,255,0.55);
        font-size: 13px;
        padding-bottom: 20px;
    """)
    subtitle.setAlignment(Qt.AlignCenter)
    ll.addWidget(subtitle)

    # Кнопка записи
    listen_btn = PulseButton()
    ll.addWidget(listen_btn)

    status_lbl = QLabel("Нажми кнопку и говори")
    status_lbl.setStyleSheet("""
        color: rgba(255,255,255,0.75);
        font-size: 14px;
        padding: 10px;
    """)
    status_lbl.setAlignment(Qt.AlignCenter)
    ll.addWidget(status_lbl)

    # Текстовый ввод
    ll.addSpacing(20)

    text_hint = QLabel("Или введи команду текстом:")
    text_hint.setStyleSheet("""
        color: rgba(255,255,255,0.45);
        font-size: 11px;
    """)
    text_hint.setAlignment(Qt.AlignCenter)
    ll.addWidget(text_hint)

    text_input = QLineEdit()
    text_input.setPlaceholderText("открой браузер…")
    text_input.setFixedWidth(340)
    text_input.setStyleSheet("""
        QLineEdit {
            background: rgba(255,255,255,0.08);
            color: white;
            border: 1px solid rgba(255,255,255,0.15);
            border-radius: 10px;
            padding: 10px 14px;
            font-size: 13px;
        }
        QLineEdit:focus { border: 1px solid rgba(110,198,255,0.6); }
    """)
    ll.addWidget(text_input)

    ll.addStretch(1)

    # Подсказки
    examples = QLabel(
        "Примеры команд:\n"
        "• «Открой браузер»\n"
        "• «Который час»\n"
        "• «Погода»\n"
        "• «Найди файл»\n"
        "• «Напиши заметку купить молоко»\n"
        "• «Закрой все окна»"
    )
    examples.setStyleSheet("""
        color: rgba(255,255,255,0.45);
        font-size: 11px;
        line-height: 1.7;
        padding: 12px;
        background: rgba(0,0,0,0.20);
        border-radius: 10px;
    """)
    examples.setAlignment(Qt.AlignLeft)
    ll.addWidget(examples)

    h.addWidget(left, 3)

    # ============================================================
    #  Правая панель — история
    # ============================================================
    right = QWidget()
    right.setFixedWidth(320)
    right.setStyleSheet("""
        background: rgba(255,255,255,0.04);
        border-left: 1px solid rgba(255,255,255,0.08);
    """)
    rl = QVBoxLayout(right)
    rl.setContentsMargins(14, 20, 14, 20)
    rl.setSpacing(10)

    hist_title = QLabel("📜  История команд")
    hist_title.setStyleSheet("color: white; font-size: 14px; font-weight: 600;")
    rl.addWidget(hist_title)

    hist_list = QListWidget()
    hist_list.setStyleSheet("""
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
            padding: 8px 10px;
            border-radius: 6px;
            border-bottom: 1px solid rgba(255,255,255,0.04);
        }
        QListWidget::item:hover { background: rgba(255,255,255,0.08); }
    """)
    rl.addWidget(hist_list, 1)

    clear_hist_btn = QPushButton("🗑  Очистить историю")
    clear_hist_btn.setCursor(Qt.PointingHandCursor)
    clear_hist_btn.setFixedHeight(34)
    clear_hist_btn.setStyleSheet("""
        QPushButton {
            background: rgba(255,107,138,0.15);
            color: #FFA0B4;
            border: 1px solid rgba(255,107,138,0.45);
            border-radius: 10px;
            font-size: 11px;
        }
        QPushButton:hover { background: rgba(255,107,138,0.35); color: white; }
    """)
    rl.addWidget(clear_hist_btn)

    h.addWidget(right)

    # ============================================================
    #  Логика
    # ============================================================

    def refresh_history():
        hist_list.clear()
        for entry in reversed(st["history"][-50:]):
            t = entry.get("time", "")
            cmd = entry.get("command", "")
            resp = entry.get("response", "")
            item = QListWidgetItem(f"🕐 {t}    «{cmd}»\n   → {resp[:60]}")
            hist_list.addItem(item)

    def say(text: str):
        if st["speaker"] is not None and st["speaker"].isRunning():
            return
        speaker = Speaker(text)
        st["speaker"] = speaker
        speaker.start()

    def handle_command(text: str, source: str = "voice"):
        if not text.strip():
            return

        response = processor.process(text)

        st["history"].append({
            "time": datetime.now().strftime("%H:%M:%S"),
            "command": text,
            "response": response,
            "source": source,
        })
        save_history()
        refresh_history()

        status_lbl.setText(f"💬 «{text}»\n🤖 {response}")
        say(response)

        if desktop and hasattr(desktop, "notifications"):
            desktop.notifications.push(f"🎤 {text[:40]}", response[:80])

    def start_listening():
        if st["listening"]:
            return

        st["listening"] = True
        listen_btn.setEnabled(False)
        listen_btn.set_recording(True)
        status_lbl.setText("🎤 Слушаю…")

        def on_recognized(text):
            st["listening"] = False
            listen_btn.setEnabled(True)
            listen_btn.set_recording(False)
            handle_command(text, "voice")

        def on_error(err):
            st["listening"] = False
            listen_btn.setEnabled(True)
            listen_btn.set_recording(False)
            status_lbl.setText(f"⚠ {err}")

        def on_status(s):
            status_lbl.setText(s)

        listener = Listener(language="ru-RU", duration=5)
        st["listener"] = listener
        listener.recognized.connect(on_recognized)
        listener.error.connect(on_error)
        listener.status.connect(on_status)
        listener.start()

    def on_text_command():
        text = text_input.text().strip()
        if not text:
            return
        text_input.clear()
        handle_command(text, "text")

    listen_btn.clicked.connect(start_listening)
    text_input.returnPressed.connect(on_text_command)

    def clear_history():
        st["history"] = []
        save_history()
        refresh_history()

    clear_hist_btn.clicked.connect(clear_history)

    refresh_history()

    return root