"""
MountOS — Онлайн-радио.

Каталог 50 000+ радиостанций через открытый API radio-browser.info:
  • Поиск станций по названию, стране, жанру
  • Воспроизведение через QMediaPlayer
  • Избранные станции (сохраняются в VFS)
  • Недавно слушанные
  • Громкость, пауза/плей
  • Интеграция с медиапанелью MountOS

API работает без ключа:
    https://de1.api.radio-browser.info/json/stations/search

Установка: apps/radio.py + перезапуск MountOS.
"""

import json
import urllib.request
import urllib.parse

from PySide6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QLabel,
                                QPushButton, QLineEdit, QListWidget,
                                QListWidgetItem, QComboBox, QScrollArea,
                                QFrame, QMessageBox, QSlider, QTabWidget,
                                QMenu, QSizePolicy)
from PySide6.QtCore import Qt, QTimer, QThread, Signal, QUrl
from PySide6.QtGui import QIcon, QAction
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput

from ui.icons import get_icon
from ui.settings_state import state
from ui.context_menu import make_menu

APP_NAME = "Радио"
APP_ICON = "music"
APP_VERSION = "1.0"
APP_AUTHOR = "MountOS"


FAVORITES_PATH = "/Notes/radio_favorites.json"
RECENT_PATH = "/Notes/radio_recent.json"
MAX_RECENT = 20


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


# ============================================================
#  Воркер поиска
# ============================================================

class RadioSearchWorker(QThread):
    """Ищет радиостанции через radio-browser.info."""

    data_ready = Signal(list)
    error = Signal(str)

    def __init__(self, query: str = "", country: str = "",
                 tag: str = "", limit: int = 50):
        super().__init__()
        self.query = query
        self.country = country
        self.tag = tag
        self.limit = limit

    def run(self):
        try:
            params = {
                "limit": self.limit,
                "hidebroken": "true",
                "order": "clickcount",
                "reverse": "true",
            }
            if self.query:
                params["name"] = self.query
            if self.country:
                params["countrycode"] = self.country
            if self.tag:
                params["tag"] = self.tag

            # Используем любой рабочий сервер radio-browser
            servers = [
                "de1.api.radio-browser.info",
                "nl1.api.radio-browser.info",
                "at1.api.radio-browser.info",
            ]
            last_err = None
            for host in servers:
                try:
                    url = f"https://{host}/json/stations/search?" + \
                          urllib.parse.urlencode(params)
                    req = urllib.request.Request(
                        url, headers={"User-Agent": "MountOS/1.0"})
                    with urllib.request.urlopen(req, timeout=10) as resp:
                        data = json.loads(resp.read().decode("utf-8"))
                    self.data_ready.emit(data)
                    return
                except Exception as e:
                    last_err = e
                    continue

            self.error.emit(str(last_err or "не удалось подключиться"))
        except Exception as e:
            self.error.emit(str(e))


# ============================================================
#  Хранилище избранного / недавнего
# ============================================================

class RadioStore:
    def __init__(self, vfs):
        self.vfs = vfs
        self.favorites = self._load(FAVORITES_PATH, [])
        self.recent = self._load(RECENT_PATH, [])

    def _load(self, path, default):
        if self.vfs is None:
            return default
        try:
            raw = self.vfs.read_text(path, "")
            if not raw.strip():
                return default
            data = json.loads(raw)
            return data if isinstance(data, list) else default
        except Exception:
            return default

    def _save(self, path, data):
        if self.vfs is None:
            return
        try:
            self.vfs.mkdir("/Notes")
            self.vfs.write_text(path, json.dumps(data, ensure_ascii=False, indent=2))
        except Exception as e:
            print(f"[Radio] save: {e}")

    def is_favorite(self, station_uuid: str) -> bool:
        return any(f.get("stationuuid") == station_uuid for f in self.favorites)

    def add_favorite(self, station: dict):
        if self.is_favorite(station.get("stationuuid", "")):
            return
        self.favorites.append(station)
        self._save(FAVORITES_PATH, self.favorites)

    def remove_favorite(self, station_uuid: str):
        self.favorites = [f for f in self.favorites
                          if f.get("stationuuid") != station_uuid]
        self._save(FAVORITES_PATH, self.favorites)

    def add_recent(self, station: dict):
        uuid = station.get("stationuuid", "")
        self.recent = [r for r in self.recent
                       if r.get("stationuuid") != uuid]
        self.recent.insert(0, station)
        self.recent = self.recent[:MAX_RECENT]
        self._save(RECENT_PATH, self.recent)

    def clear_recent(self):
        self.recent = []
        self._save(RECENT_PATH, [])


# ============================================================
#  Основное приложение
# ============================================================

def build():
    root = QWidget()
    h = QHBoxLayout(root)
    h.setContentsMargins(0, 0, 0, 0)
    h.setSpacing(0)

    vfs = _get_vfs(root)
    store = RadioStore(vfs)

    # ---- Плеер ----
    player = QMediaPlayer(root)
    audio = QAudioOutput(root)
    player.setAudioOutput(audio)
    audio.setVolume(0.7)

    # ============================================================
    #  Левая панель — поиск + список
    # ============================================================
    side = QWidget()
    side.setFixedWidth(380)
    side.setStyleSheet("""
        background: rgba(255,255,255,0.04);
        border-right: 1px solid rgba(255,255,255,0.08);
    """)
    sl = QVBoxLayout(side)
    sl.setContentsMargins(14, 16, 14, 16)
    sl.setSpacing(10)

    title = QLabel("📻  Онлайн-радио")
    title.setStyleSheet("color: white; font-size: 16px; font-weight: 600; padding: 2px;")
    sl.addWidget(title)

    # Поиск
    search_row = QHBoxLayout()
    search_row.setSpacing(8)

    search_input = QLineEdit()
    search_input.setPlaceholderText("Название станции…")
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
    search_row.addWidget(search_input, 1)

    search_btn = QPushButton("🔍")
    search_btn.setFixedSize(36, 36)
    search_btn.setCursor(Qt.PointingHandCursor)
    search_btn.setStyleSheet("""
        QPushButton {
            background: rgba(110,198,255,0.22);
            color: white;
            border: 1px solid rgba(110,198,255,0.55);
            border-radius: 10px;
            font-size: 15px;
        }
        QPushButton:hover { background: rgba(110,198,255,0.42); }
    """)
    search_row.addWidget(search_btn)

    sl.addLayout(search_row)

    # Фильтры
    filters_row = QHBoxLayout()
    filters_row.setSpacing(8)

    country_combo = QComboBox()
    country_combo.addItem("🌍 Все страны", "")
    for code, name in [
        ("RU", "🇷🇺 Россия"),
        ("US", "🇺🇸 США"),
        ("GB", "🇬🇧 Великобритания"),
        ("DE", "🇩🇪 Германия"),
        ("FR", "🇫🇷 Франция"),
        ("UA", "🇺🇦 Украина"),
        ("KZ", "🇰🇿 Казахстан"),
        ("BY", "🇧🇾 Беларусь"),
        ("IT", "🇮🇹 Италия"),
        ("ES", "🇪🇸 Испания"),
        ("JP", "🇯🇵 Япония"),
    ]:
        country_combo.addItem(name, code)
    country_combo.setStyleSheet("""
        QComboBox {
            background: rgba(255,255,255,0.08);
            color: white;
            border: 1px solid rgba(255,255,255,0.15);
            border-radius: 10px;
            padding: 6px 10px;
            font-size: 11px;
        }
        QComboBox:hover { background: rgba(255,255,255,0.14); }
        QComboBox QAbstractItemView {
            background: rgba(28,34,54,0.98);
            color: white;
            selection-background-color: rgba(110,198,255,0.35);
        }
    """)
    filters_row.addWidget(country_combo, 1)

    tag_combo = QComboBox()
    tag_combo.addItem("🎵 Любой жанр", "")
    for tag in ["pop", "rock", "jazz", "classical", "news", "dance",
                "electronic", "hiphop", "metal", "chillout", "oldies",
                "talk", "lounge", "folk"]:
        tag_combo.addItem(f"🎵 {tag}", tag)
    tag_combo.setStyleSheet(country_combo.styleSheet())
    filters_row.addWidget(tag_combo, 1)

    sl.addLayout(filters_row)

    # Табы: результаты / избранное / недавние
    tabs = QTabWidget()
    tabs.setStyleSheet("""
        QTabWidget::pane {
            background: transparent;
            border: none;
        }
        QTabBar::tab {
            background: rgba(255,255,255,0.04);
            color: rgba(255,255,255,0.65);
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 8px;
            padding: 6px 12px;
            margin: 2px 2px;
            font-size: 11px;
            min-width: 80px;
        }
        QTabBar::tab:selected {
            background: rgba(110,198,255,0.22);
            color: white;
            border: 1px solid rgba(110,198,255,0.50);
        }
        QTabBar::tab:hover:!selected {
            background: rgba(255,255,255,0.10);
            color: white;
        }
    """)

    def make_station_list():
        lw = QListWidget()
        lw.setStyleSheet("""
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
            }
            QListWidget::item:hover { background: rgba(255,255,255,0.08); }
            QListWidget::item:selected { background: rgba(110,198,255,0.30); }
        """)
        return lw

    results_list = make_station_list()
    favorites_list = make_station_list()
    recent_list = make_station_list()

    tabs.addTab(results_list, "🔍 Результаты")
    tabs.addTab(favorites_list, "⭐ Избранное")
    tabs.addTab(recent_list, "🕐 Недавние")

    sl.addWidget(tabs, 1)

    # Статус
    status_lbl = QLabel("Введи название или выбери фильтр")
    status_lbl.setStyleSheet("color: rgba(255,255,255,0.55); font-size: 11px;")
    sl.addWidget(status_lbl)

    h.addWidget(side)

    # ============================================================
    #  Правая панель — плеер
    # ============================================================
    right = QWidget()
    rl = QVBoxLayout(right)
    rl.setContentsMargins(30, 30, 30, 30)
    rl.setSpacing(20)

    # Иконка-заставка
    cover = QLabel("📻")
    cover.setAlignment(Qt.AlignCenter)
    cover.setFixedSize(220, 220)
    cover.setStyleSheet("""
        background: rgba(255,255,255,0.04);
        border: 1px solid rgba(255,255,255,0.10);
        border-radius: 110px;
        font-size: 100px;
    """)
    cover_wrap = QHBoxLayout()
    cover_wrap.addStretch(1)
    cover_wrap.addWidget(cover)
    cover_wrap.addStretch(1)
    rl.addLayout(cover_wrap)

    # Название станции
    station_lbl = QLabel("Ничего не играет")
    station_lbl.setAlignment(Qt.AlignCenter)
    station_lbl.setStyleSheet("""
        color: white;
        font-size: 20px;
        font-weight: 600;
    """)
    station_lbl.setWordWrap(True)
    rl.addWidget(station_lbl)

    # Страна / жанр
    meta_lbl = QLabel("—")
    meta_lbl.setAlignment(Qt.AlignCenter)
    meta_lbl.setStyleSheet("""
        color: rgba(255,255,255,0.55);
        font-size: 13px;
    """)
    rl.addWidget(meta_lbl)

    rl.addSpacing(14)

    # Кнопки управления
    ctrl = QHBoxLayout()
    ctrl.setSpacing(14)
    ctrl.setAlignment(Qt.AlignCenter)

    def make_ctrl(icon_name, tooltip, callback, size=48):
        b = QPushButton()
        b.setFixedSize(size, size)
        b.setToolTip(tooltip)
        b.setCursor(Qt.PointingHandCursor)
        b.setIcon(QIcon(get_icon(icon_name, int(size * 0.45), "#FFFFFF")))
        b.setIconSize(__import__("PySide6.QtCore", fromlist=["QSize"]).QSize(int(size * 0.4), int(size * 0.4)))
        b.setStyleSheet(f"""
            QPushButton {{
                background: rgba(255,255,255,0.06);
                border: 1px solid rgba(255,255,255,0.10);
                border-radius: {size // 2}px;
            }}
            QPushButton:hover {{
                background: rgba(255,255,255,0.18);
            }}
            QPushButton:pressed {{
                background: rgba(110,198,255,0.35);
            }}
        """)
        b.clicked.connect(callback)
        return b

    play_btn = QPushButton()
    play_btn.setFixedSize(72, 72)
    play_btn.setCursor(Qt.PointingHandCursor)
    play_btn.setIcon(QIcon(get_icon("grid", 30, "#FFFFFF")))
    play_btn.setIconSize(__import__("PySide6.QtCore", fromlist=["QSize"]).QSize(28, 28))
    play_btn.setStyleSheet("""
        QPushButton {
            background: rgba(110,198,255,0.30);
            border: 1px solid rgba(110,198,255,0.65);
            border-radius: 36px;
        }
        QPushButton:hover { background: rgba(110,198,255,0.50); }
    """)
    ctrl.addWidget(play_btn)

    fav_btn = make_ctrl("star", "В избранное", lambda: toggle_favorite())
    ctrl.addWidget(fav_btn)

    rl.addLayout(ctrl)

    rl.addSpacing(20)

    # Громкость
    vol_row = QHBoxLayout()
    vol_row.setSpacing(10)

    vol_icon = QLabel()
    vol_icon.setPixmap(get_icon("music", 18, "#FFFFFF"))
    vol_row.addWidget(vol_icon)

    vol_slider = QSlider(Qt.Horizontal)
    vol_slider.setRange(0, 100)
    vol_slider.setValue(70)
    vol_slider.setStyleSheet("""
        QSlider::groove:horizontal {
            height: 4px;
            background: rgba(255,255,255,0.12);
            border-radius: 2px;
        }
        QSlider::sub-page:horizontal {
            background: rgba(110,198,255,0.75);
            border-radius: 2px;
        }
        QSlider::handle:horizontal {
            background: white;
            width: 12px;
            margin: -4px 0;
            border-radius: 6px;
        }
    """)
    vol_row.addWidget(vol_slider, 1)

    vol_pct = QLabel("70%")
    vol_pct.setStyleSheet("color: rgba(255,255,255,0.6); font-size: 11px; min-width: 40px;")
    vol_row.addWidget(vol_pct)

    rl.addLayout(vol_row)

    rl.addStretch(1)

    h.addWidget(right, 1)

    # ============================================================
    #  Логика
    # ============================================================

    st = {
        "current_station": None,
        "search_worker": None,
    }

    def refresh_favorites():
        favorites_list.clear()
        for s in store.favorites:
            add_station_to_list(favorites_list, s, is_fav=True)

    def refresh_recent():
        recent_list.clear()
        for s in store.recent:
            add_station_to_list(recent_list, s)

    def add_station_to_list(lw: QListWidget, s: dict, is_fav: bool = False):
        name = s.get("name", "?")
        country = s.get("country", "")
        codec = s.get("codec", "")
        bitrate = s.get("bitrate", 0)

        # Флаг страны (если есть)
        country_code = s.get("countrycode", "")
        flag = ""
        if country_code:
            # Преобразуем код в эмодзи-флаг
            try:
                flag = "".join(chr(ord(c) + 127397) for c in country_code.upper())
                flag += " "
            except Exception:
                flag = ""

        bitrate_str = f"{bitrate} kbps" if bitrate else ""
        codec_str = codec.upper() if codec else ""
        tag_str = " · ".join(filter(None, [bitrate_str, codec_str]))

        text = f"{flag}{name[:35]}"
        if country:
            text += f"\n   {country[:25]}"
        if tag_str:
            text += f"  ·  {tag_str}"

        if is_fav:
            text = "⭐ " + text

        item = QListWidgetItem(text)
        item.setData(Qt.UserRole, s)
        lw.addItem(item)

    # ---- Поиск ----
    def do_search():
        query = search_input.text().strip()
        country = country_combo.currentData() or ""
        tag = tag_combo.currentData() or ""

        if not query and not country and not tag:
            status_lbl.setText("Введи название или выбери фильтр")
            return

        status_lbl.setText("Поиск…")
        results_list.clear()
        item = QListWidgetItem("⏳ Идёт поиск…")
        results_list.addItem(item)

        worker = RadioSearchWorker(query=query, country=country,
                                    tag=tag, limit=60)
        st["search_worker"] = worker
        worker.data_ready.connect(on_search_results)
        worker.error.connect(on_search_error)
        worker.start()

    def on_search_results(results):
        results_list.clear()
        if not results:
            results_list.addItem("Ничего не найдено")
            status_lbl.setText("Ничего не найдено")
            return
        for s in results:
            add_station_to_list(results_list, s)
        status_lbl.setText(f"Найдено {len(results)} станций")

    def on_search_error(err):
        results_list.clear()
        results_list.addItem(f"⚠ {err}")
        status_lbl.setText(f"Ошибка: {err[:60]}")

    # ---- Воспроизведение ----
    def play_station(s: dict):
        url = s.get("url_resolved") or s.get("url", "")
        if not url:
            QMessageBox.warning(root, "Радио", "У станции нет URL потока")
            return

        st["current_station"] = s

        name = s.get("name", "?")
        country = s.get("country", "")
        tags = s.get("tags", "")
        bitrate = s.get("bitrate", 0)
        codec = s.get("codec", "")

        station_lbl.setText(name)
        meta_lbl.setText(" · ".join(filter(None, [
            country, tags.split(",")[0] if tags else "",
            f"{bitrate} kbps" if bitrate else "",
            codec.upper() if codec else "",
        ])))

        player.setSource(QUrl(url))
        player.play()
        play_btn.setIcon(QIcon(get_icon("notes", 30, "#FFFFFF")))

        # Сохраняем в недавние
        store.add_recent(s)
        refresh_recent()

        # Обновляем индикатор избранного
        update_fav_icon()

        # Интеграция с медиапанелью MountOS
        try:
            from ui.media_panel import player_state
            player_state().set_track(
                title=name,
                artist=country or "Radio",
                duration_ms=0,
                source="radio",
            )
            player_state().set_state(playing=True)
        except Exception:
            pass

        status_lbl.setText(f"▶ {name}")

    def toggle_favorite():
        s = st["current_station"]
        if s is None:
            return
        uuid = s.get("stationuuid", "")
        if store.is_favorite(uuid):
            store.remove_favorite(uuid)
        else:
            store.add_favorite(s)
        refresh_favorites()
        update_fav_icon()

    def update_fav_icon():
        s = st["current_station"]
        if s is None:
            return
        uuid = s.get("stationuuid", "")
        if store.is_favorite(uuid):
            fav_btn.setIcon(QIcon(get_icon("star_filled", 22, "#FFB86C")))
        else:
            fav_btn.setIcon(QIcon(get_icon("star", 22, "#FFFFFF")))

    def play_pause():
        if player.playbackState() == QMediaPlayer.PlayingState:
            player.pause()
            play_btn.setIcon(QIcon(get_icon("grid", 30, "#FFFFFF")))
            try:
                from ui.media_panel import player_state
                player_state().set_state(playing=False)
            except Exception:
                pass
        else:
            player.play()
            play_btn.setIcon(QIcon(get_icon("notes", 30, "#FFFFFF")))
            try:
                from ui.media_panel import player_state
                player_state().set_state(playing=True)
            except Exception:
                pass

    # ---- Клики по станциям ----
    def on_results_click(item):
        s = item.data(Qt.UserRole)
        if s:
            play_station(s)

    def on_favorites_click(item):
        s = item.data(Qt.UserRole)
        if s:
            play_station(s)

    def on_recent_click(item):
        s = item.data(Qt.UserRole)
        if s:
            play_station(s)

    # ---- Контекстное меню ----
    def show_context_menu(lw: QListWidget, pos, in_favorites: bool = False):
        item = lw.itemAt(pos)
        if item is None:
            return
        s = item.data(Qt.UserRole)
        if not s:
            return

        menu = make_menu(lw)
        a_play = menu.addAction("▶ Воспроизвести")
        a_play.triggered.connect(lambda: play_station(s))

        uuid = s.get("stationuuid", "")
        if store.is_favorite(uuid):
            a_fav = menu.addAction("★ Убрать из избранного")
            a_fav.triggered.connect(lambda: (
                store.remove_favorite(uuid), refresh_favorites()))
        else:
            a_fav = menu.addAction("☆ В избранное")
            a_fav.triggered.connect(lambda: (
                store.add_favorite(s), refresh_favorites()))

        menu.addSeparator()

        # Копировать URL
        url = s.get("url_resolved") or s.get("url", "")
        if url:
            a_url = menu.addAction("📋 Копировать URL")
            from PySide6.QtWidgets import QApplication
            a_url.triggered.connect(
                lambda: QApplication.clipboard().setText(url))

        menu.exec(lw.mapToGlobal(pos))

    # ---- Связи ----
    search_btn.clicked.connect(do_search)
    search_input.returnPressed.connect(do_search)
    country_combo.currentIndexChanged.connect(do_search)
    tag_combo.currentIndexChanged.connect(do_search)
    play_btn.clicked.connect(play_pause)
    fav_btn.clicked.connect(toggle_favorite)
    results_list.itemClicked.connect(on_results_click)
    favorites_list.itemClicked.connect(on_favorites_click)
    recent_list.itemClicked.connect(on_recent_click)

    # Контекстные меню
    for lw, in_fav in [(results_list, False), (favorites_list, True),
                       (recent_list, False)]:
        lw.setContextMenuPolicy(Qt.CustomContextMenu)
        lw.customContextMenuRequested.connect(
            lambda pos, w=lw, f=in_fav: show_context_menu(w, pos, f))

    # ---- Громкость ----
    def set_volume(v):
        audio.setVolume(v / 100.0)
        vol_pct.setText(f"{v}%")

    vol_slider.valueChanged.connect(set_volume)
    set_volume(70)

    # ---- Player callbacks ----
    def on_player_error(*args):
        status_lbl.setText("⚠ Ошибка воспроизведения")
        play_btn.setIcon(QIcon(get_icon("grid", 30, "#FFFFFF")))

    player.errorOccurred.connect(on_player_error)

    # ---- Автопоиск при старте ----
    def initial_search():
        # Популярные российские станции по умолчанию
        status_lbl.setText("Загрузка популярных станций…")
        worker = RadioSearchWorker(country="RU", limit=50)
        st["search_worker"] = worker
        worker.data_ready.connect(on_search_results)
        worker.error.connect(on_search_error)
        worker.start()

    QTimer.singleShot(300, initial_search)
    refresh_favorites()
    refresh_recent()

    return root