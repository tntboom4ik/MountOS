"""
MountOS — Музыка.
Плеер из VFS: плейлист, воспроизведение mp3/wav/ogg/flac/m4a,
перемотка, громкость, повтор, случайный порядок.
"""
import os
import random
from PySide6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QLabel,
                                QPushButton, QListWidget, QListWidgetItem,
                                QFileDialog, QSlider, QMessageBox, QSizePolicy)
from PySide6.QtCore import Qt, QSize, QTimer, QUrl, QTime
from PySide6.QtGui import QIcon
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput

from ui.icons import get_icon
from ui.settings_state import state

APP_NAME = "Музыка"
APP_ICON = "globe"
APP_VERSION = "1.0"
APP_AUTHOR = "MountOS"


SUPPORTED_EXT = {".mp3", ".wav", ".ogg", ".flac", ".m4a", ".aac", ".opus"}


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


def _fmt_time(ms: int) -> str:
    if ms is None or ms < 0:
        ms = 0
    s = ms // 1000
    return f"{s // 60}:{s % 60:02d}"


# ============================================================
#  Основное приложение
# ============================================================

def build():
    root = QWidget()
    h = QHBoxLayout(root)
    h.setContentsMargins(0, 0, 0, 0)
    h.setSpacing(0)

    # ---------- Плеер ----------
    player = QMediaPlayer(root)
    audio = QAudioOutput(root)
    player.setAudioOutput(audio)
    audio.setVolume(0.7)

    # ---------- Левая панель: плейлист ----------
    side = QWidget()
    side.setFixedWidth(260)
    side.setStyleSheet("""
        background: rgba(255,255,255,0.04);
        border-right: 1px solid rgba(255,255,255,0.08);
    """)
    sl = QVBoxLayout(side)
    sl.setContentsMargins(12, 14, 12, 14)
    sl.setSpacing(8)

    header = QLabel("Плейлист")
    header.setStyleSheet("color: white; font-size: 14px; font-weight: 600; padding: 2px 4px;")
    sl.addWidget(header)

    btn_row = QHBoxLayout()
    btn_row.setSpacing(6)

    refresh_btn = QPushButton("⟳")
    refresh_btn.setFixedSize(30, 30)
    refresh_btn.setToolTip("Обновить из /Music")
    refresh_btn.setCursor(Qt.PointingHandCursor)
    refresh_btn.setStyleSheet(_icon_btn_style())
    btn_row.addWidget(refresh_btn)

    import_btn = QPushButton("  Импорт с ПК")
    import_btn.setIcon(QIcon(get_icon("plus", 14, "#6EC6FF")))
    import_btn.setCursor(Qt.PointingHandCursor)
    import_btn.setFixedHeight(30)
    import_btn.setStyleSheet("""
        QPushButton {
            background: rgba(110,198,255,0.15);
            color: white;
            border: 1px solid rgba(110,198,255,0.45);
            border-radius: 8px;
            padding: 4px 10px;
            text-align: left;
            font-size: 11px;
        }
        QPushButton:hover { background: rgba(110,198,255,0.35); }
    """)
    btn_row.addWidget(import_btn, 1)

    sl.addLayout(btn_row)

    playlist = QListWidget()
    playlist.setStyleSheet("""
        QListWidget {
            background: rgba(0,0,0,0.18);
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 10px;
            color: white;
            font-size: 12px;
            outline: none;
            padding: 4px;
        }
        QListWidget::item {
            padding: 6px 8px;
            border-radius: 6px;
        }
        QListWidget::item:hover { background: rgba(255,255,255,0.08); }
        QListWidget::item:selected { background: rgba(110,198,255,0.30); }
    """)
    playlist.setIconSize(QSize(20, 20))
    sl.addWidget(playlist, 1)

    status_lbl = QLabel("Треков: 0")
    status_lbl.setStyleSheet("color: rgba(255,255,255,0.45); font-size: 11px; padding: 2px 4px;")
    sl.addWidget(status_lbl)

    h.addWidget(side)

    # ---------- Правая область: плеер ----------
    right = QWidget()
    rl = QVBoxLayout(right)
    rl.setContentsMargins(24, 20, 24, 20)
    rl.setSpacing(14)

    # Обложка-заглушка
    cover = QLabel()
    cover.setAlignment(Qt.AlignCenter)
    cover.setFixedSize(220, 220)
    cover.setStyleSheet("""
        background: rgba(255,255,255,0.04);
        border: 1px solid rgba(255,255,255,0.10);
        border-radius: 100px;
    """)
    cover.setPixmap(get_icon("globe", 100, state().get("accent")))

    cover_wrap = QHBoxLayout()
    cover_wrap.addStretch(1)
    cover_wrap.addWidget(cover)
    cover_wrap.addStretch(1)
    rl.addLayout(cover_wrap)

    rl.addSpacing(8)

    # Название трека
    title_lbl = QLabel("Ничего не играет")
    title_lbl.setAlignment(Qt.AlignCenter)
    title_lbl.setStyleSheet("""
        color: white;
        font-size: 18px;
        font-weight: 600;
    """)
    rl.addWidget(title_lbl)

    artist_lbl = QLabel("—")
    artist_lbl.setAlignment(Qt.AlignCenter)
    artist_lbl.setStyleSheet("""
        color: rgba(255,255,255,0.55);
        font-size: 12px;
    """)
    rl.addWidget(artist_lbl)

    rl.addSpacing(12)

    # Полоса перемотки
    seek_row = QHBoxLayout()
    seek_row.setSpacing(10)

    pos_lbl = QLabel("0:00")
    pos_lbl.setStyleSheet("color: rgba(255,255,255,0.6); font-size: 11px; min-width: 40px;")
    pos_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
    seek_row.addWidget(pos_lbl)

    seek = QSlider(Qt.Horizontal)
    seek.setRange(0, 1000)
    seek.setValue(0)
    seek.setStyleSheet("""
        QSlider::groove:horizontal {
            height: 5px;
            background: rgba(255,255,255,0.12);
            border-radius: 3px;
        }
        QSlider::sub-page:horizontal {
            background: #6EC6FF;
            border-radius: 3px;
        }
        QSlider::handle:horizontal {
            background: white;
            width: 12px;
            margin: -4px 0;
            border-radius: 6px;
        }
        QSlider::handle:horizontal:hover { background: #A0DEFF; }
    """)
    seek_row.addWidget(seek, 1)

    dur_lbl = QLabel("0:00")
    dur_lbl.setStyleSheet("color: rgba(255,255,255,0.6); font-size: 11px; min-width: 40px;")
    seek_row.addWidget(dur_lbl)

    rl.addLayout(seek_row)

    # Кнопки управления
    ctrl = QHBoxLayout()
    ctrl.setSpacing(14)
    ctrl.setAlignment(Qt.AlignCenter)

    shuffle_btn = QPushButton("⇄")
    shuffle_btn.setFixedSize(40, 40)
    shuffle_btn.setCheckable(True)
    shuffle_btn.setToolTip("Случайный порядок")
    shuffle_btn.setCursor(Qt.PointingHandCursor)
    shuffle_btn.setStyleSheet(_small_btn_style())
    ctrl.addWidget(shuffle_btn)

    prev_btn = QPushButton("⏮")
    prev_btn.setFixedSize(48, 48)
    prev_btn.setToolTip("Предыдущий")
    prev_btn.setCursor(Qt.PointingHandCursor)
    prev_btn.setStyleSheet(_small_btn_style())
    ctrl.addWidget(prev_btn)

    play_btn = QPushButton("▶")
    play_btn.setFixedSize(64, 64)
    play_btn.setToolTip("Играть / пауза")
    play_btn.setCursor(Qt.PointingHandCursor)
    play_btn.setStyleSheet("""
        QPushButton {
            background: rgba(110,198,255,0.30);
            color: white;
            border: 1px solid rgba(110,198,255,0.65);
            border-radius: 32px;
            font-size: 22px;
            font-weight: 600;
        }
        QPushButton:hover { background: rgba(110,198,255,0.55); }
        QPushButton:pressed { background: rgba(110,198,255,0.80); }
    """)
    ctrl.addWidget(play_btn)

    next_btn = QPushButton("⏭")
    next_btn.setFixedSize(48, 48)
    next_btn.setToolTip("Следующий")
    next_btn.setCursor(Qt.PointingHandCursor)
    next_btn.setStyleSheet(_small_btn_style())
    ctrl.addWidget(next_btn)

    repeat_btn = QPushButton("↻")
    repeat_btn.setFixedSize(40, 40)
    repeat_btn.setCheckable(True)
    repeat_btn.setToolTip("Повтор")
    repeat_btn.setCursor(Qt.PointingHandCursor)
    repeat_btn.setStyleSheet(_small_btn_style())
    ctrl.addWidget(repeat_btn)

    rl.addLayout(ctrl)

    rl.addSpacing(8)

    # Громкость
    vol_row = QHBoxLayout()
    vol_row.setSpacing(10)

    vol_icon = QLabel()
    vol_icon.setPixmap(get_icon("globe", 18, "#FFFFFF"))
    vol_row.addWidget(vol_icon)

    vol = QSlider(Qt.Horizontal)
    vol.setRange(0, 100)
    vol.setValue(70)
    vol.setFixedWidth(180)
    vol.setStyleSheet("""
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
    vol_row.addWidget(vol)

    vol_pct = QLabel("70%")
    vol_pct.setStyleSheet("color: rgba(255,255,255,0.6); font-size: 11px; min-width: 40px;")
    vol_row.addWidget(vol_pct)

    vol_row.addStretch(1)
    rl.addLayout(vol_row)

    rl.addStretch(1)

    h.addWidget(right, 1)

    # ============================================================
    #  Логика
    # ============================================================

    state_obj = {
        "items": [],       # [{name, path}]
        "current": -1,
    }

    def scan_tracks():
        """Ищет музыкальные файлы по всему VFS."""
        vfs = _get_vfs(root)
        if vfs is None:
            return []
        found = []

        def walk(path, depth=0):
            if depth > 6:
                return
            try:
                items = vfs.listdir(path)
            except Exception:
                return
            for it in items:
                if it["is_dir"]:
                    walk(it["path"], depth + 1)
                else:
                    ext = os.path.splitext(it["name"])[1].lower()
                    if ext in SUPPORTED_EXT:
                        found.append({"name": it["name"], "path": it["path"]})
        walk("/")
        return found

    def refresh_playlist():
        state_obj["items"] = scan_tracks()
        playlist.clear()
        for idx, it in enumerate(state_obj["items"]):
            item = QListWidgetItem(
                QIcon(get_icon("globe", 18, state().get("accent"))),
                it["name"])
            item.setData(Qt.UserRole, idx)
            playlist.addItem(item)
        status_lbl.setText(f"Треков: {len(state_obj['items'])}")

        if state_obj["items"] and state_obj["current"] < 0:
            _load_index(0)

    def _load_index(idx: int, autoplay: bool = False):
        vfs = _get_vfs(root)
        if vfs is None or not state_obj["items"]:
            return
        idx = max(0, min(idx, len(state_obj["items"]) - 1))
        state_obj["current"] = idx
        it = state_obj["items"][idx]

        # QMediaPlayer не читает из виртуальной ФС напрямую —
        # копируем во временный файл и играем его.
        import tempfile
        try:
            data = vfs.read_bytes(it["path"])
        except Exception as e:
            title_lbl.setText("Ошибка чтения")
            artist_lbl.setText(str(e))
            return

        ext = os.path.splitext(it["name"])[1] or ".mp3"
        fd, tmp_path = tempfile.mkstemp(suffix=ext, prefix="mountos_music_")
        os.close(fd)
        with open(tmp_path, "wb") as f:
            f.write(data)

        player.setSource(QUrl.fromLocalFile(tmp_path))

        name = os.path.splitext(it["name"])[0]
        title_lbl.setText(name)
        artist_lbl.setText(it["path"])

        playlist.setCurrentRow(idx)

        if autoplay:
            player.play()
            play_btn.setText("⏸")

    def play_pause():
        if not state_obj["items"]:
            return
        if player.playbackState() == QMediaPlayer.PlayingState:
            player.pause()
            play_btn.setText("▶")
        else:
            if state_obj["current"] < 0:
                _load_index(0)
            player.play()
            play_btn.setText("⏸")

    def play_index(idx: int):
        _load_index(idx, autoplay=True)
        play_btn.setText("⏸")

    def next_track():
        if not state_obj["items"]:
            return
        if shuffle_btn.isChecked():
            idx = random.randrange(len(state_obj["items"]))
        else:
            idx = (state_obj["current"] + 1) % len(state_obj["items"])
        play_index(idx)

    def prev_track():
        if not state_obj["items"]:
            return
        if shuffle_btn.isChecked():
            idx = random.randrange(len(state_obj["items"]))
        else:
            idx = (state_obj["current"] - 1) % len(state_obj["items"])
        play_index(idx)

    # ---- Связи ----
    playlist.itemClicked.connect(
        lambda item: play_index(int(item.data(Qt.UserRole))))
    play_btn.clicked.connect(play_pause)
    next_btn.clicked.connect(next_track)
    prev_btn.clicked.connect(prev_track)
    refresh_btn.clicked.connect(refresh_playlist)

    # ---- Позиция / длительность ----
    def on_duration(dur):
        dur_lbl.setText(_fmt_time(dur))

    def on_position(pos):
        pos_lbl.setText(_fmt_time(pos))
        dur = player.duration()
        if dur > 0:
            seek.blockSignals(True)
            seek.setValue(int(pos * 1000 / dur))
            seek.blockSignals(False)

    def on_seek(value):
        dur = player.duration()
        if dur > 0:
            player.setPosition(int(value * dur / 1000))

    player.durationChanged.connect(on_duration)
    player.positionChanged.connect(on_position)
    seek.sliderMoved.connect(on_seek)

    # ---- Конец трека ----
    def on_status(status):
        if status == QMediaPlayer.EndOfMedia:
            if repeat_btn.isChecked():
                player.setPosition(0)
                player.play()
            else:
                next_track()

    player.mediaStatusChanged.connect(on_status)

    # ---- Громкость ----
    def set_volume(v):
        audio.setVolume(v / 100.0)
        vol_pct.setText(f"{v}%")

    vol.valueChanged.connect(set_volume)
    set_volume(70)

    # ---- Импорт с ПК ----
    def import_from_pc():
        vfs = _get_vfs(root)
        if vfs is None:
            return
        files, _ = QFileDialog.getOpenFileNames(
            root, "Импортировать музыку", "",
            "Аудио (*.mp3 *.wav *.ogg *.flac *.m4a *.aac *.opus);;Все файлы (*)")
        if not files:
            return
        target = "/Music"
        vfs.mkdir(target)
        imported = 0
        for src in files:
            name = os.path.basename(src)
            try:
                with open(src, "rb") as f:
                    data = f.read()
                vfs.write_bytes(vfs.join(target, name), data)
                imported += 1
            except Exception as e:
                print(f"[Music] импорт {name}: {e}")
        d = _get_desktop(root)
        if d:
            d.notifications.push("Импортировано",
                                 f"{imported} треков → /Music")
        refresh_playlist()

    import_btn.clicked.connect(import_from_pc)

    # ---- Первичная загрузка ----
    refresh_playlist()

    return root


# ============================================================
#  Стили
# ============================================================

def _icon_btn_style():
    return """
        QPushButton {
            background: rgba(255,255,255,0.08);
            color: white;
            border: 1px solid rgba(255,255,255,0.14);
            border-radius: 8px;
            font-size: 14px;
        }
        QPushButton:hover { background: rgba(255,255,255,0.20); }
        QPushButton:pressed { background: rgba(110,198,255,0.35); }
    """


def _small_btn_style():
    return """
        QPushButton {
            background: rgba(255,255,255,0.06);
            color: white;
            border: 1px solid rgba(255,255,255,0.10);
            border-radius: 20px;
            font-size: 16px;
        }
        QPushButton:hover {
            background: rgba(255,255,255,0.20);
            border: 1px solid rgba(255,255,255,0.24);
        }
        QPushButton:pressed { background: rgba(110,198,255,0.35); }
        QPushButton:checked {
            background: rgba(110,198,255,0.30);
            border: 1px solid rgba(110,198,255,0.70);
        }
    """