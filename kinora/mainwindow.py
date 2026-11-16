"""Main window: video, control bar, playlist dock, context menu and all commands."""

import os
import tempfile
import time

from PySide6.QtCore import QEvent, QPoint, QSize, Qt, QTimer, qVersion
from PySide6.QtGui import QAction, QCursor, QGuiApplication, QImage, QKeySequence
from PySide6.QtWidgets import (QApplication, QDialog, QDialogButtonBox, QDockWidget,
                               QFileDialog, QInputDialog, QMainWindow, QMenu, QMessageBox,
                               QPlainTextEdit, QVBoxLayout, QWidget)

from . import APP_NAME, __version__
from .actions import ACTIONS, BY_ID, keys_for
from .engine import Engine
from .icons import app_icon
from .mpvwidget import MpvGLWidget, NativeVideoWidget
from .playlist import PlaylistPanel, expand_targets
from .thumbnailer import Thumbnailer
from .util import (AUDIO_EXTS, SUB_EXTS, VIDEO_EXTS, display_name, fmt_time, is_subtitle,
                   is_url, media_in_folder, normalize_target)
from .widgets import ControlBar, ThumbPopup

ASPECTS = [("Default", "-1"), ("16:9", "16:9"), ("4:3", "4:3"), ("2.35:1", "2.35:1"),
           ("1.85:1", "1.85:1"), ("16:10", "16:10"), ("5:4", "5:4"), ("1:1", "1:1")]
CROPS = [("None", None), ("16:9", 16 / 9), ("1.85:1", 1.85), ("2.35:1", 2.35), ("2.39:1", 2.39),
         ("4:3", 4 / 3)]
SPEEDS = [0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 3.0, 4.0]


class VideoArea(QWidget):
    """Hosts the video surface and the control bar; overlays the bar in fullscreen."""

    def __init__(self, controls: ControlBar):
        super().__init__()
        self.video = None
        self.controls = controls
        controls.setParent(self)
        self.overlay = False
        self.setAttribute(Qt.WA_StyledBackground)
        self.setStyleSheet("VideoArea { background: black; }")

    def set_video(self, video):
        self.video = video
        video.setParent(self)
        video.lower()
        self.relayout()

    def set_overlay(self, on):
        self.overlay = on
        self.controls.set_translucent(on)
        self.relayout()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.relayout()

    def relayout(self):
        w, h = self.width(), self.height()
        ch = self.controls.sizeHint().height()
        shown = self.controls.isVisibleTo(self)
        if self.video is not None:
            vh = h if (self.overlay or not shown) else h - ch
            self.video.setGeometry(0, 0, w, max(1, vh))
        self.controls.setGeometry(0, h - ch, w, ch)
        self.controls.raise_()


class MainWindow(QMainWindow):
    def __init__(self, settings, resume, debug=False):
        super().__init__()
        self.s = settings
        self.resume = resume
        self.current = None
        self.tracks = []
        self._fit_pending = False
        self._resume_osd = None
        self._queued_subs = []
        self._thumb_for = None
        self._show_remaining = False
        self._was_maximized = False
        self._dock_was_visible = False
        self._last_cursor = QPoint()
        self._last_move = time.monotonic()
        self._cursor_hidden = False
        self._hover = None  # (anchor, text)

        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(app_icon())
        self.setAcceptDrops(True)
        self.resize(960, 600)
        self.setMinimumSize(360, 240)

        # -- video + engine ------------------------------------------------------------
        self.controls = ControlBar()
        self.area = VideoArea(self.controls)
        self.setCentralWidget(self.area)
        from .config import video_surface
        if video_surface(settings) == "native":
            self.video = NativeVideoWidget()
            self.area.set_video(self.video)
            self.engine = Engine(settings, wid=int(self.video.winId()), debug=debug, parent=self)
        else:
            self.engine = Engine(settings, debug=debug, parent=self)
            self.video = MpvGLWidget(self.engine.mpv)
            self.area.set_video(self.video)
        self.engine.prop_changed.connect(self._on_prop)
        self.video.installEventFilter(self)
        self.video.customContextMenuRequested.connect(
            lambda pos: self.show_menu(self.video.mapToGlobal(pos)))
        self.video.setFocus()
        self._gl_ready = self.video.is_native
        self._pending_load = None
        if not self.video.is_native:
            self.video.ready.connect(self._on_gl_ready)

        # -- playlist dock -------------------------------------------------------------
        self.playlist = PlaylistPanel(settings)
        self.playlist.add_requested = self._playlist_add_files
        self.playlist.play_requested.connect(self.play_index)
        self.dock = QDockWidget("Playlist", self)
        self.dock.setObjectName("playlist")
        self.dock.setWidget(self.playlist)
        self.dock.setFeatures(QDockWidget.DockWidgetClosable | QDockWidget.DockWidgetMovable |
                              QDockWidget.DockWidgetFloatable)
        self.addDockWidget(Qt.RightDockWidgetArea, self.dock)
        self.dock.hide()
        self.dock.visibilityChanged.connect(self.controls.btn_playlist.setChecked)

        # -- thumbnails ----------------------------------------------------------------
        self.thumbs = Thumbnailer(parent=self)
        self.thumbs.ready.connect(self._on_thumb)
        self.popup = ThumbPopup(self.area)
        if self.video.is_native:
            self.popup.setAttribute(Qt.WA_NativeWindow)  # must stack above mpv's native window

        # -- control wiring ------------------------------------------------------------
        c = self.controls
        c.btn_menu.clicked.connect(lambda: self.show_menu(
            c.btn_menu.mapToGlobal(QPoint(0, 0)), above=c.btn_menu))
        c.btn_open.clicked.connect(self.open_file_dialog)
        c.btn_prev.clicked.connect(self.prev_file)
        c.btn_play.clicked.connect(self.play_pause)
        c.btn_stop.clicked.connect(self.stop)
        c.btn_next.clicked.connect(self.next_file)
        c.btn_playlist.clicked.connect(self.toggle_playlist)
        c.btn_full.clicked.connect(self.toggle_fullscreen)
        c.btn_mute.clicked.connect(lambda: self.engine.command("cycle", "mute"))
        c.volume.setMaximum(int(settings["volume_max"]))
        c.volume.valueChanged.connect(lambda v: self.engine.set("volume", float(v)))
        c.seek.seek_requested.connect(self._seek_to)
        c.seek.hovered.connect(self._on_seek_hover)
        c.seek.hover_left.connect(self._on_seek_leave)
        c.time_label.clicked.connect(self._toggle_remaining)
        vol = float(settings["volume"]) if settings["remember_volume"] else 100.0
        self._set_volume_ui(vol)
        c.set_muted(bool(settings["muted"]) if settings["remember_volume"] else False)

        # -- actions / shortcuts -------------------------------------------------------
        self.acts: dict[str, QAction] = {}
        handlers = self._handlers()
        for a in ACTIONS:
            act = QAction(a.label, self)
            act.setCheckable(a.checkable)
            act.setShortcutContext(Qt.WindowShortcut)
            fn = handlers[a.id]
            act.triggered.connect(lambda _=False, fn=fn: fn())
            self.addAction(act)
            self.acts[a.id] = act
        self.apply_shortcuts()

        # -- timers --------------------------------------------------------------------
        self._pos_timer = QTimer(self, interval=200, timeout=self._update_position)
        self._pos_timer.start()
        self._ui_timer = QTimer(self, interval=150, timeout=self._update_ui_visibility)
        self._ui_timer.start()
        self._click_timer = QTimer(self, singleShot=True, timeout=self._single_click)
        self._click_timer.setInterval(QApplication.styleHints().mouseDoubleClickInterval())
        self._save_timer = QTimer(self, interval=60000, timeout=self._periodic_save)
        self._save_timer.start()

    # ===================================================================================
    # actions
    # ===================================================================================
    def _handlers(self):
        s = self.s
        e = self.engine
        return {
            "open_file": self.open_file_dialog,
            "open_folder": self.open_folder_dialog,
            "open_url": self.open_url_dialog,
            "open_subtitle": self.open_subtitle_dialog,
            "open_audio": self.open_audio_dialog,
            "close_file": self.close_file,
            "media_info": self.media_info,
            "preferences": self.preferences,
            "quit": self.close,
            "play_pause": self.play_pause,
            "stop": self.stop,
            "prev_file": self.prev_file,
            "next_file": self.next_file,
            "seek_back_fine": lambda: self.seek_rel(-s["seek_fine"]),
            "seek_fwd_fine": lambda: self.seek_rel(s["seek_fine"]),
            "seek_back_small": lambda: self.seek_rel(-s["seek_small"]),
            "seek_fwd_small": lambda: self.seek_rel(s["seek_small"]),
            "seek_back_medium": lambda: self.seek_rel(-s["seek_medium"]),
            "seek_fwd_medium": lambda: self.seek_rel(s["seek_medium"]),
            "seek_back_large": lambda: self.seek_rel(-s["seek_large"]),
            "seek_fwd_large": lambda: self.seek_rel(s["seek_large"]),
            "seek_start": lambda: self._seek_to(0, True),
            "goto_time": self.goto_time,
            "frame_next": lambda: e.command("frame-step"),
            "frame_prev": lambda: e.command("frame-back-step"),
            "chapter_prev": lambda: self.chapter_step(-1),
            "chapter_next": lambda: self.chapter_step(1),
            "speed_up": lambda: self.set_speed(e.get("speed", 1.0) + s["speed_step"]),
            "speed_down": lambda: self.set_speed(e.get("speed", 1.0) - s["speed_step"]),
            "speed_reset": lambda: self.set_speed(1.0),
            "ab_set_a": self.ab_set_a,
            "ab_set_b": self.ab_set_b,
            "ab_clear": self.ab_clear,
            "repeat_cycle": self.cycle_repeat,
            "shuffle": self.toggle_shuffle,
            "volume_up": lambda: self.change_volume(s["volume_step"]),
            "volume_down": lambda: self.change_volume(-s["volume_step"]),
            "mute": lambda: e.command("cycle", "mute"),
            "audio_next": lambda: self.cycle_track("audio"),
            "audio_delay_minus": lambda: self.add_delay("audio-delay", -0.1, "Audio"),
            "audio_delay_plus": lambda: self.add_delay("audio-delay", 0.1, "Audio"),
            "audio_delay_reset": lambda: self.add_delay("audio-delay", None, "Audio"),
            "normalize": self.toggle_normalize,
            "pitch_correction": self.toggle_pitch,
            "sub_toggle": self.toggle_subs,
            "sub_next": lambda: self.cycle_track("sub"),
            "sub_delay_minus": lambda: self.add_delay("sub-delay", -0.5, "Subtitle"),
            "sub_delay_plus": lambda: self.add_delay("sub-delay", 0.5, "Subtitle"),
            "sub_delay_reset": lambda: self.add_delay("sub-delay", None, "Subtitle"),
            "sub_bigger": lambda: self.sub_scale(0.1),
            "sub_smaller": lambda: self.sub_scale(-0.1),
            "sub_up": lambda: self.sub_move(-2),
            "sub_down": lambda: self.sub_move(2),
            "aspect_cycle": self.cycle_aspect,
            "zoom_in": lambda: self.zoom(0.1),
            "zoom_out": lambda: self.zoom(-0.1),
            "zoom_reset": self.zoom_reset,
            "fill_window": self.toggle_fill,
            "rotate_cw": lambda: self.rotate(90),
            "rotate_ccw": lambda: self.rotate(-90),
            "flip_h": lambda: self.toggle_vf("hflip", "Horizontal flip"),
            "flip_v": lambda: self.toggle_vf("vflip", "Vertical flip"),
            "deinterlace": self.toggle_deinterlace,
            "hwdec_toggle": self.toggle_hwdec,
            "brightness_down": lambda: self.adjust("brightness", -2),
            "brightness_up": lambda: self.adjust("brightness", 2),
            "contrast_down": lambda: self.adjust("contrast", -2),
            "contrast_up": lambda: self.adjust("contrast", 2),
            "saturation_down": lambda: self.adjust("saturation", -2),
            "saturation_up": lambda: self.adjust("saturation", 2),
            "hue_down": lambda: self.adjust("hue", -2),
            "hue_up": lambda: self.adjust("hue", 2),
            "picture_reset": self.picture_reset,
            "screenshot": lambda: self.screenshot(True),
            "screenshot_clean": lambda: self.screenshot(False),
            "copy_frame": self.copy_frame,
            "fullscreen": self.toggle_fullscreen,
            "exit_fullscreen": self.exit_fullscreen,
            "on_top_cycle": self.cycle_on_top,
            "size_50": lambda: self.fit_window(0.5),
            "size_100": lambda: self.fit_window(1.0),
            "size_150": lambda: self.fit_window(1.5),
            "size_200": lambda: self.fit_window(2.0),
            "playlist_toggle": self.toggle_playlist,
            "osd_info": self.osd_info,
        }

    def apply_shortcuts(self):
        overrides = self.s["keys"] or {}
        for aid, act in self.acts.items():
            act.setShortcuts([QKeySequence(k) for k in keys_for(aid, overrides) if k])

    # ===================================================================================
    # opening
    # ===================================================================================
    def open_targets(self, paths, append=False):
        paths = [p for p in paths if p]
        if not paths:
            return
        subs = [p for p in paths if not is_url(p) and is_subtitle(p)]
        media = [p for p in paths if p not in subs]
        if subs and not media:
            if self.current:
                for sp in subs:
                    self.engine.command("sub-add", normalize_target(sp), "select")
                self.engine.osd("Subtitle loaded: " + os.path.basename(subs[-1]))
            return
        expanded = expand_targets(media)
        if not expanded:
            self.engine.osd("Nothing playable found")
            return
        self._queued_subs = [normalize_target(sp) for sp in subs]
        if append:
            idx = self.playlist.add_paths(expanded)
            if not self.current and idx >= 0:
                self.play_index(idx)
            return
        single = len(media) == 1 and len(expanded) == 1 and not is_url(expanded[0]) \
            and not os.path.isdir(normalize_target(media[0]))
        if single and self.s["auto_add_folder"]:
            target = expanded[0]
            siblings = media_in_folder(os.path.dirname(target))
            if target in siblings:
                self.playlist.set_paths(siblings)
                self.play_index(siblings.index(target))
                return
        self.playlist.set_paths(expanded)
        self.play_index(0)

    def play_index(self, i):
        path = self.playlist.path_at(i)
        if path is None:
            return
        self.playlist.set_current(i)
        self.load(path)

    def _on_gl_ready(self, recreated):
        self._gl_ready = True
        if recreated and self.current:
            # mpv drops video when its renderer is freed; bring it back on the new one.
            if not self.engine.get("vid"):
                self.engine.set("vid", "auto")
            self.engine.command("video-reload")
        if self._pending_load:
            path, self._pending_load = self._pending_load, None
            self.load(path)

    def load(self, path):
        if not self._gl_ready:
            # libmpv cannot start video before the OpenGL renderer exists (first paint).
            self._pending_load = path
            self.current = path
            return
        self._remember_position()  # no-op unless something is actually playing
        self.current = path
        start = self.resume.get(path) if self.s["resume_playback"] else None
        self.engine.set("start", f"{start:.2f}" if start else "none")
        self.engine.set("ab-loop-a", "no")
        self.engine.set("ab-loop-b", "no")
        self.engine.command("loadfile", path, "replace")
        self.engine.set("pause", False)
        self.controls.set_playing(True)
        self._resume_osd = start
        self._fit_pending = True
        self._thumb_for = None
        self.thumbs.close()
        self.s.add_recent(path)
        self.setWindowTitle(f"{display_name(path)} — {APP_NAME}")

    def _media_filter(self):
        vid = " ".join("*" + x for x in sorted(VIDEO_EXTS))
        aud = " ".join("*" + x for x in sorted(AUDIO_EXTS))
        sub = " ".join("*" + x for x in sorted(SUB_EXTS))
        return (f"Media files ({vid} {aud});;Video ({vid});;Audio ({aud});;"
                f"Subtitles ({sub});;All files (*)")

    def _start_dir(self):
        if self.current and not is_url(self.current):
            return os.path.dirname(self.current)
        return os.path.expanduser("~")

    def open_file_dialog(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Open", self._start_dir(), self._media_filter())
        if files:
            self.open_targets(files)

    def _playlist_add_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Add to playlist", self._start_dir(),
                                                self._media_filter())
        if files:
            self.open_targets(files, append=True)

    def open_folder_dialog(self):
        d = QFileDialog.getExistingDirectory(self, "Open folder", self._start_dir())
        if d:
            self.open_targets([d])

    def open_url_dialog(self):
        clip = QGuiApplication.clipboard().text().strip()
        url, ok = QInputDialog.getText(self, "Open URL",
                                       "URL (http, https, rtsp, ...; YouTube etc. need yt-dlp):",
                                       text=clip if is_url(clip) else "")
        if ok and url.strip():
            self.open_targets([url.strip()])

    def open_subtitle_dialog(self):
        if not self.current:
            return
        sub = " ".join("*" + x for x in sorted(SUB_EXTS))
        files, _ = QFileDialog.getOpenFileNames(self, "Load subtitle", self._start_dir(),
                                                f"Subtitles ({sub});;All files (*)")
        for f in files:
            self.engine.command("sub-add", f, "select")
        if files:
            self.engine.osd("Subtitle loaded: " + os.path.basename(files[-1]))

    def open_audio_dialog(self):
        if not self.current:
            return
        aud = " ".join("*" + x for x in sorted(AUDIO_EXTS))
        files, _ = QFileDialog.getOpenFileNames(self, "Load audio track", self._start_dir(),
                                                f"Audio ({aud});;All files (*)")
        for f in files:
            self.engine.command("audio-add", f, "select")

    # ===================================================================================
    # playback commands
    # ===================================================================================
    def _single_click(self):
        if self.current:
            self.play_pause()

    def play_pause(self):
        if not self.current:
            if self.playlist.count():
                self.play_index(max(0, self.playlist.current_index()))
            else:
                self.open_file_dialog()
            return
        if self.engine.get("eof-reached"):
            self._seek_to(0, True)
            self.engine.set("pause", False)
            return
        self.engine.command("cycle", "pause")

    def stop(self):
        self._remember_position()
        self.engine.command("stop")
        self.current = None
        self._reset_ui()

    def close_file(self):
        self.stop()
        self.playlist.set_current(-1)

    def next_file(self):
        i = self.playlist.next_index(auto=False)
        if i is not None:
            self.play_index(i)

    def prev_file(self):
        i = self.playlist.prev_index()
        if i is not None:
            self.play_index(i)

    def seek_rel(self, secs):
        if not self.current:
            return
        self.engine.command("seek", secs, "relative")
        pos = self.engine.get("time-pos")
        dur = self.engine.get("duration")
        if pos is not None:
            self.engine.osd(f"{'+' if secs > 0 else '−'}{abs(secs):g}s   {fmt_time(pos)} / {fmt_time(dur)}")

    def _seek_to(self, t, exact):
        if self.current:
            self.engine.command("seek", float(t), "absolute" if exact else "absolute+keyframes")

    def goto_time(self):
        if not self.current:
            return
        cur = fmt_time(self.engine.get("time-pos", 0), hours=True)
        txt, ok = QInputDialog.getText(self, "Go to time", "Time (h:mm:ss, mm:ss, seconds or 50%):",
                                       text=cur)
        if not ok:
            return
        txt = txt.strip()
        try:
            if txt.endswith("%"):
                self.engine.command("seek", float(txt[:-1]), "absolute-percent")
                return
            secs = 0.0
            for part in txt.split(":"):
                secs = secs * 60 + float(part)
            self._seek_to(secs, True)
        except ValueError:
            QMessageBox.warning(self, "Go to time", f"Could not understand “{txt}”.")

    def chapter_step(self, d):
        if self.engine.command("add", "chapter", d):
            ch = self.engine.get("chapter")
            chapters = self.engine.get("chapter-list", [])
            if isinstance(ch, int) and 0 <= ch < len(chapters):
                self.engine.osd(f"Chapter {ch + 1}: {chapters[ch].get('title', '')}")

    def set_speed(self, v):
        v = max(0.1, min(8.0, round(float(v), 2)))
        self.engine.set("speed", v)
        self.engine.osd(f"Speed: {v:.2f}x")

    def ab_set_a(self):
        pos = self.engine.get("time-pos")
        if pos is None:
            return
        self.engine.set("ab-loop-a", pos)
        self.engine.osd(f"A-B repeat start: {fmt_time(pos)}")

    def ab_set_b(self):
        pos = self.engine.get("time-pos")
        if pos is None:
            return
        a = self.engine.get("ab-loop-a")
        if not isinstance(a, (int, float)):
            return self.ab_set_a()
        if pos <= a:
            self.engine.osd("A-B repeat: end must be after start")
            return
        self.engine.set("ab-loop-b", pos)
        self.engine.osd(f"A-B repeat: {fmt_time(a)} → {fmt_time(pos)}")

    def ab_clear(self):
        self.engine.set("ab-loop-a", "no")
        self.engine.set("ab-loop-b", "no")
        self.engine.osd("A-B repeat off")

    def cycle_repeat(self):
        mode = self.playlist.cycle_repeat()
        self.engine.osd({"off": "Repeat: off", "all": "Repeat: playlist",
                         "one": "Repeat: current file"}[mode])

    def set_repeat(self, mode):
        self.s["repeat"] = mode
        self.playlist.sync_mode_buttons()

    def toggle_shuffle(self):
        self.s["shuffle"] = not self.s["shuffle"]
        self.playlist.sync_mode_buttons()
        self.engine.osd("Shuffle: " + ("on" if self.s["shuffle"] else "off"))

    # -- audio --------------------------------------------------------------------------
    def change_volume(self, d):
        v = max(0.0, min(float(self.s["volume_max"]), self.engine.get("volume", 100.0) + d))
        self.engine.set("volume", v)
        if self.engine.get("mute"):
            self.engine.set("mute", False)
        self.engine.osd(f"Volume: {v:.0f}%")

    def _set_volume_ui(self, v):
        c = self.controls
        c.volume.blockSignals(True)
        c.volume.setValue(int(round(v)))
        c.volume.blockSignals(False)
        c.vol_label.setText(f"{v:.0f}%")

    def add_delay(self, prop, d, what):
        if d is None:
            self.engine.set(prop, 0.0)
        else:
            self.engine.command("add", prop, d)
        v = self.engine.get(prop, 0.0)
        self.engine.osd(f"{what} delay: {v * 1000:+.0f} ms")

    def toggle_normalize(self):
        self.s["normalize"] = not self.s["normalize"]
        self.engine.set_normalize(self.s["normalize"])
        self.engine.osd("Normalize volume: " + ("on" if self.s["normalize"] else "off"))

    def toggle_pitch(self):
        self.s["pitch_correction"] = not self.s["pitch_correction"]
        self.engine.set("audio-pitch-correction", self.s["pitch_correction"])
        self.engine.osd("Keep pitch: " + ("on" if self.s["pitch_correction"] else "off"))

    def _track_label(self, t):
        parts = [f"{t.get('id')}:"]
        if t.get("title"):
            parts.append(t["title"])
        if t.get("lang"):
            parts.append(f"[{t['lang']}]")
        if t.get("codec"):
            parts.append(f"({t['codec']})")
        if t.get("external"):
            parts.append("external")
        if len(parts) == 1:
            parts.append("Track")
        return " ".join(parts)

    def cycle_track(self, kind):
        prop = {"audio": "aid", "sub": "sid"}[kind]
        self.engine.command("cycle", kind)
        cur = self.engine.get(prop)
        for t in self.engine.get("track-list", []):
            if t.get("type") == ("audio" if kind == "audio" else "sub") and t.get("id") == cur:
                self.engine.osd(("Audio: " if kind == "audio" else "Subtitle: ") + self._track_label(t))
                return
        self.engine.osd(("Audio" if kind == "audio" else "Subtitles") + ": off")

    def select_track(self, prop, tid):
        self.engine.set(prop, tid if tid is not None else "no")

    # -- subtitles ----------------------------------------------------------------------
    def toggle_subs(self):
        v = not self.engine.get("sub-visibility", True)
        self.engine.set("sub-visibility", v)
        self.engine.osd("Subtitles: " + ("shown" if v else "hidden"))

    def sub_scale(self, d):
        v = max(0.3, min(4.0, round(self.engine.get("sub-scale", 1.0) + d, 2)))
        self.engine.set("sub-scale", v)
        self.s["sub_scale"] = v
        self.engine.osd(f"Subtitle size: {v * 100:.0f}%")

    def sub_move(self, d):
        v = max(0, min(150, int(self.engine.get("sub-pos", 100)) + d))
        self.engine.set("sub-pos", v)
        self.s["sub_pos"] = v
        self.engine.osd(f"Subtitle position: {v}")

    # -- video --------------------------------------------------------------------------
    def set_aspect(self, value, label=None):
        self.engine.set("video-aspect-override", value)
        self.engine.osd("Aspect ratio: " + (label or value))

    def cycle_aspect(self):
        cur = str(self.engine.get("video-aspect-override", "-1"))
        values = [v for _, v in ASPECTS]
        try:
            cur_f = float(cur)
        except ValueError:
            cur_f = None
        idx = 0
        for i, (_, v) in enumerate(ASPECTS):
            if v == cur or (cur_f is not None and v != "-1" and _ratio(v) and
                            abs(_ratio(v) - cur_f) < 0.01):
                idx = i
                break
        nxt = (idx + 1) % len(values)
        self.set_aspect(ASPECTS[nxt][1], ASPECTS[nxt][0])

    def set_crop(self, ratio, label):
        self.engine.command("vf", "remove", "@crop")
        if ratio is None:
            self.engine.set("video-crop", "")
            self.engine.osd("Crop: none")
            return
        vp = self.engine.get("video-params") or {}
        w, h = vp.get("w"), vp.get("h")
        if not w or not h:
            return
        if w / h > ratio:
            cw, ch = int(h * ratio) & ~1, h
        else:
            cw, ch = w, int(w / ratio) & ~1
        x, y = (w - cw) // 2, (h - ch) // 2
        if not self.engine.set("video-crop", f"{cw}x{ch}+{x}+{y}"):
            self._ensure_sw_frames()
            self.engine.command("vf", "add", f"@crop:crop={cw}:{ch}:{x}:{y}")
        self.engine.osd(f"Crop: {label}")

    def zoom(self, d):
        v = round(self.engine.get("video-zoom", 0.0) + d, 2)
        self.engine.set("video-zoom", v)
        self.engine.osd(f"Zoom: {2 ** v * 100:.0f}%")

    def zoom_reset(self):
        for p, v in (("video-zoom", 0.0), ("video-pan-x", 0.0), ("video-pan-y", 0.0), ("panscan", 0.0)):
            self.engine.set(p, v)
        self.set_crop(None, "none")
        self.engine.osd("Zoom / crop reset")

    def toggle_fill(self):
        v = 0.0 if self.engine.get("panscan", 0.0) > 0 else 1.0
        self.engine.set("panscan", v)
        self.engine.osd("Crop to fill window: " + ("on" if v else "off"))

    def rotate(self, d):
        v = (int(self.engine.get("video-rotate", 0)) + d) % 360
        self.engine.set("video-rotate", v)
        self.engine.osd(f"Rotation: {v}°")
        QTimer.singleShot(150, lambda: self.fit_window() if self.s["fit_window_to_video"] else None)

    def _vf_has(self, label):
        for f in self.engine.get("vf", []) or []:
            if isinstance(f, dict) and f.get("label") == label:
                return True
        return False

    def _ensure_sw_frames(self):
        """CPU video filters can't take GPU-resident frames; switch hwdec to copy-back mode."""
        cur = self.engine.get("hwdec-current") or "no"
        if cur != "no" and not cur.endswith("-copy"):
            self.engine.set("hwdec", "auto-copy-safe")

    def toggle_vf(self, name, what):
        if not self._vf_has(name):
            self._ensure_sw_frames()
        self.engine.command("vf", "toggle", f"@{name}:{name}")
        self.engine.osd(f"{what}: " + ("on" if self._vf_has(name) else "off"))

    def toggle_deinterlace(self):
        cur = self.engine.get("deinterlace", False)
        on = not (cur is True or cur == "yes")
        self.engine.set("deinterlace", on)
        self.engine.osd("Deinterlace: " + ("on" if on else "off"))

    def toggle_hwdec(self):
        cur = self.engine.get("hwdec", "no")
        if cur in ("no", False):
            want = self.s["hwdec"] if self.s["hwdec"] != "no" else "auto-safe"
        else:
            want = "no"
        self.engine.set("hwdec", want)
        self.engine.osd("Hardware decoding: " + ("off" if want == "no" else want))

    def adjust(self, prop, d):
        v = max(-100, min(100, int(self.engine.get(prop, 0)) + d))
        self.engine.set(prop, v)
        self.engine.osd(f"{prop.capitalize()}: {v:+d}")

    def picture_reset(self):
        for p in ("brightness", "contrast", "saturation", "hue", "gamma"):
            self.engine.set(p, 0)
        self.engine.osd("Picture adjustments reset")

    def screenshot(self, with_subs):
        if not self.current:
            return
        d = self.engine.get("screenshot-directory")
        if d:
            os.makedirs(os.path.expanduser(d), exist_ok=True)
        self.engine.command("screenshot", "subtitles" if with_subs else "video")

    def copy_frame(self):
        if not self.current:
            return
        path = os.path.join(tempfile.gettempdir(), f"kinora-clip-{os.getpid()}.png")
        if self.engine.command("screenshot-to-file", path, "subtitles"):
            img = QImage(path)
            if not img.isNull():
                QGuiApplication.clipboard().setImage(img)
                self.engine.osd("Frame copied to clipboard")
            try:
                os.remove(path)
            except OSError:
                pass

    # -- view ---------------------------------------------------------------------------
    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.exit_fullscreen()
        else:
            self._was_maximized = self.isMaximized()
            self._dock_was_visible = self.dock.isVisible() and not self.dock.isFloating()
            if self._dock_was_visible:
                self.dock.hide()
            self.showFullScreen()

    def exit_fullscreen(self):
        if not self.isFullScreen():
            return
        if self._was_maximized:
            self.showMaximized()
        else:
            self.showNormal()
        if self._dock_was_visible:
            self.dock.show()

    def changeEvent(self, e):
        if e.type() == QEvent.WindowStateChange:
            fs = self.isFullScreen()
            self.controls.set_fullscreen(fs)
            self.area.set_overlay(fs and not self.video.is_native)
            self.controls.setVisible(not fs)
            self.area.relayout()
        super().changeEvent(e)

    def set_on_top_mode(self, mode):
        self.s["on_top"] = mode
        self.apply_on_top()
        self.engine.osd({"never": "Always on top: off", "always": "Always on top: on",
                         "playing": "Always on top: while playing"}[mode])

    def cycle_on_top(self):
        order = ["never", "always", "playing"]
        cur = self.s["on_top"] if self.s["on_top"] in order else "never"
        self.set_on_top_mode(order[(order.index(cur) + 1) % 3])

    def apply_on_top(self):
        mode = self.s["on_top"]
        playing = bool(self.current) and not self.engine.get("pause", True)
        want = mode == "always" or (mode == "playing" and playing)
        wh = self.windowHandle()
        if wh is None:
            return
        if bool(wh.flags() & Qt.WindowStaysOnTopHint) != want:
            # Changing the QWindow flag avoids re-creating the native window (keeps mpv's surface).
            wh.setFlag(Qt.WindowStaysOnTopHint, want)

    def toggle_playlist(self):
        self.dock.setVisible(not self.dock.isVisible())

    def osd_info(self):
        if not self.current:
            return
        self.engine.command(
            "show-text",
            "${media-title}\n${time-pos} / ${duration} (${percent-pos}%)\n"
            "Speed ${speed}x   Volume ${volume}%   HW ${hwdec-current}\n"
            "${video-params/w}x${video-params/h} ${video-codec}   ${audio-codec-name}", 3500)

    def fit_window(self, scale=None):
        vp = self.engine.get("video-params")
        if not vp or self.isFullScreen():
            return
        if self.isMaximized():
            if scale is None:
                return
            self.showNormal()
        dw, dh = vp.get("dw") or vp.get("w"), vp.get("dh") or vp.get("h")
        if not dw or not dh:
            return
        rot = (int(self.engine.get("video-rotate", 0)) + int(vp.get("rotate", 0) or 0)) % 180
        if rot == 90:
            dw, dh = dh, dw
        dpr = self.devicePixelRatioF() or 1.0
        w, h = dw / dpr, dh / dpr
        if scale:
            w, h = w * scale, h * scale
        avail = self.screen().availableGeometry()
        frame_w = self.frameGeometry().width() - self.width()
        frame_h = self.frameGeometry().height() - self.height()
        extra_h = 0 if self.area.overlay else self.controls.sizeHint().height()
        extra_w = self.dock.width() if (self.dock.isVisible() and not self.dock.isFloating()) else 0
        pct = 1.0 if scale else max(20, min(100, int(self.s["max_window_percent"]))) / 100.0
        maxw = avail.width() * pct - frame_w - extra_w
        maxh = avail.height() * pct - frame_h - extra_h
        f = min(1.0, maxw / w, maxh / h)
        w, h = max(320, int(w * f)), max(180, int(h * f))
        self.resize(w + extra_w, h + extra_h)
        # keep the window on screen
        g = self.frameGeometry()
        x = min(max(g.left(), avail.left()), max(avail.left(), avail.right() - g.width()))
        y = min(max(g.top(), avail.top()), max(avail.top(), avail.bottom() - g.height()))
        if (x, y) != (g.left(), g.top()):
            self.move(x, y)

    # ===================================================================================
    # dialogs
    # ===================================================================================
    def preferences(self):
        from .prefs import PreferencesDialog
        old_output = self.s["video_surface"]
        old_conf = self.s["load_mpv_config"]
        dlg = PreferencesDialog(self.s, self)
        if dlg.exec() == QDialog.Accepted:
            self.apply_settings()
            self.s.save()
            if self.s["video_surface"] != old_output or self.s["load_mpv_config"] != old_conf:
                QMessageBox.information(self, "Preferences",
                                        "Some changes take effect after restarting Kinora.")

    def apply_settings(self):
        self.engine.apply_settings(self.s)
        self.controls.volume.setMaximum(int(self.s["volume_max"]))
        self.playlist.sync_mode_buttons()
        self.apply_shortcuts()
        self.apply_on_top()
        if not self.s["thumbnails"]:
            self.thumbs.close()
            self._thumb_for = None

    def media_info(self):
        e = self.engine
        if not self.current:
            return
        lines = [f"File: {self.current}", f"Title: {e.get('media-title', '')}",
                 f"Container: {e.get('file-format', '?')}",
                 f"Duration: {fmt_time(e.get('duration'), hours=True)}",
                 f"Size: {_human(e.get('file-size'))}", ""]
        vp = e.get("video-params") or {}
        if vp:
            lines += ["[Video]",
                      f"Codec: {e.get('video-codec', '?')}",
                      f"Resolution: {vp.get('w')}x{vp.get('h')}  (display {vp.get('dw')}x{vp.get('dh')})",
                      f"Pixel format: {vp.get('pixelformat', '?')}  {vp.get('colormatrix', '')} "
                      f"{vp.get('primaries', '')} {vp.get('gamma', '')}",
                      f"Frame rate: {e.get('container-fps', '?')}",
                      f"Bitrate: {_kbps(e.get('video-bitrate'))}",
                      f"Hardware decoding: {e.get('hwdec-current', 'no') or 'no'}",
                      f"Video output: {e.get('current-vo', '?')}", ""]
        ap = e.get("audio-params") or {}
        if ap:
            lines += ["[Audio]",
                      f"Codec: {e.get('audio-codec', '?')}",
                      f"Sample rate: {ap.get('samplerate')} Hz   Channels: {ap.get('hr-channels') or ap.get('channel-count')}",
                      f"Format: {ap.get('format')}", f"Bitrate: {_kbps(e.get('audio-bitrate'))}",
                      f"Output: {e.get('current-ao', '?')}", ""]
        lines.append("[Tracks]")
        for t in e.get("track-list", []):
            sel = "*" if t.get("selected") else " "
            lines.append(f" {sel} {t.get('type'):5} {self._track_label(t)}")
        chapters = e.get("chapter-list", [])
        if chapters:
            lines += ["", "[Chapters]"] + [f" {fmt_time(c.get('time'), hours=True)}  {c.get('title', '')}"
                                            for c in chapters]
        dlg = QDialog(self)
        dlg.setWindowTitle("Media Information")
        dlg.resize(640, 480)
        txt = QPlainTextEdit("\n".join(str(x) for x in lines))
        txt.setReadOnly(True)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(dlg.reject)
        copy = bb.addButton("Copy", QDialogButtonBox.ActionRole)
        copy.clicked.connect(lambda: QGuiApplication.clipboard().setText(txt.toPlainText()))
        lay = QVBoxLayout(dlg)
        lay.addWidget(txt)
        lay.addWidget(bb)
        dlg.exec()

    # ===================================================================================
    # context menu
    # ===================================================================================
    def show_menu(self, global_pos, above=None):
        m = self.build_menu()
        if above is not None:
            global_pos = above.mapToGlobal(QPoint(0, -m.sizeHint().height()))
        m.exec(global_pos)

    def _sync_checks(self):
        e = self.engine
        a = self.acts
        a["fullscreen"].setChecked(self.isFullScreen())
        a["mute"].setChecked(bool(e.get("mute")))
        a["sub_toggle"].setChecked(bool(e.get("sub-visibility", True)))
        a["normalize"].setChecked(bool(self.s["normalize"]))
        a["pitch_correction"].setChecked(bool(self.s["pitch_correction"]))
        a["shuffle"].setChecked(bool(self.s["shuffle"]))
        a["flip_h"].setChecked(self._vf_has("hflip"))
        a["flip_v"].setChecked(self._vf_has("vflip"))
        d = e.get("deinterlace", False)
        a["deinterlace"].setChecked(d is True or d == "yes")
        a["hwdec_toggle"].setChecked(e.get("hwdec", "no") not in ("no", False))
        a["fill_window"].setChecked(e.get("panscan", 0.0) > 0)
        a["playlist_toggle"].setChecked(self.dock.isVisible())

    def build_menu(self):
        self._sync_checks()
        a = self.acts
        e = self.engine
        has = bool(self.current)
        m = QMenu(self)

        # Open
        om = m.addMenu("Open")
        for k in ("open_file", "open_folder", "open_url"):
            om.addAction(a[k])
        om.addSeparator()
        om.addAction(a["open_subtitle"])
        om.addAction(a["open_audio"])
        rm = om.addMenu("Recent Files")
        recent = self.s["recent"]
        for r in recent:
            rm.addAction(display_name(r), lambda r=r: self.open_targets([r]))
        if recent:
            rm.addSeparator()
            rm.addAction("Clear List", lambda: self.s.__setitem__("recent", []))
        else:
            rm.addAction("(empty)").setEnabled(False)
        om.addSeparator()
        om.addAction(a["close_file"])

        m.addSeparator()
        m.addAction(a["play_pause"])
        m.addAction(a["stop"])
        m.addAction(a["prev_file"])
        m.addAction(a["next_file"])

        # Playback
        pm = m.addMenu("Playback")
        for k in ("seek_back_small", "seek_fwd_small", "seek_back_medium", "seek_fwd_medium",
                  "seek_back_large", "seek_fwd_large", "seek_start", "goto_time"):
            pm.addAction(a[k])
        pm.addSeparator()
        pm.addAction(a["frame_prev"])
        pm.addAction(a["frame_next"])
        sm = pm.addMenu("Speed")
        cur_speed = e.get("speed", 1.0)
        for sp in SPEEDS:
            act = sm.addAction(f"{sp:g}x", lambda sp=sp: self.set_speed(sp))
            act.setCheckable(True)
            act.setChecked(abs(cur_speed - sp) < 0.001)
        sm.addSeparator()
        for k in ("speed_up", "speed_down", "speed_reset"):
            sm.addAction(a[k])
        abm = pm.addMenu("A-B Repeat")
        for k in ("ab_set_a", "ab_set_b", "ab_clear"):
            abm.addAction(a[k])
        chapters = e.get("chapter-list", []) if has else []
        cm = pm.addMenu("Chapters")
        cm.setEnabled(bool(chapters))
        cur_ch = e.get("chapter")
        for i, c in enumerate(chapters):
            act = cm.addAction(f"{fmt_time(c.get('time'))}  {c.get('title') or f'Chapter {i + 1}'}",
                               lambda i=i: self.engine.set("chapter", i))
            act.setCheckable(True)
            act.setChecked(i == cur_ch)
        if chapters:
            cm.addSeparator()
            cm.addAction(a["chapter_prev"])
            cm.addAction(a["chapter_next"])
        pm.addSeparator()
        rpm = pm.addMenu("Repeat")
        for mode, label in (("off", "Off"), ("one", "Current File"), ("all", "Playlist")):
            act = rpm.addAction(label, lambda mode=mode: self.set_repeat(mode))
            act.setCheckable(True)
            act.setChecked(self.s["repeat"] == mode)
        pm.addAction(a["shuffle"])

        # Audio
        am = m.addMenu("Audio")
        at = [t for t in self.tracks if t.get("type") == "audio"]
        for t in at:
            act = am.addAction(self._track_label(t), lambda t=t: self.select_track("aid", t.get("id")))
            act.setCheckable(True)
            act.setChecked(bool(t.get("selected")))
        if at:
            am.addSeparator()
        for k in ("audio_next", "volume_up", "volume_down", "mute"):
            am.addAction(a[k])
        am.addSeparator()
        for k in ("audio_delay_minus", "audio_delay_plus", "audio_delay_reset"):
            am.addAction(a[k])
        am.addSeparator()
        am.addAction(a["normalize"])
        am.addAction(a["pitch_correction"])
        am.addAction(a["open_audio"])

        # Subtitles
        subm = m.addMenu("Subtitles")
        st = [t for t in self.tracks if t.get("type") == "sub"]
        off = subm.addAction("Off", lambda: self.select_track("sid", None))
        off.setCheckable(True)
        cur_sid = e.get("sid")
        off.setChecked(not cur_sid)
        for t in st:
            act = subm.addAction(self._track_label(t), lambda t=t: self.select_track("sid", t.get("id")))
            act.setCheckable(True)
            act.setChecked(t.get("id") == cur_sid)
        if st:
            sec = subm.addMenu("Secondary Subtitle")
            cur2 = e.get("secondary-sid")
            o2 = sec.addAction("Off", lambda: self.engine.set("secondary-sid", "no"))
            o2.setCheckable(True)
            o2.setChecked(not cur2)
            for t in st:
                act = sec.addAction(self._track_label(t),
                                    lambda t=t: self.engine.set("secondary-sid", t.get("id")))
                act.setCheckable(True)
                act.setChecked(t.get("id") == cur2)
        subm.addSeparator()
        subm.addAction(a["open_subtitle"])
        subm.addAction(a["sub_toggle"])
        subm.addAction(a["sub_next"])
        subm.addSeparator()
        for k in ("sub_delay_minus", "sub_delay_plus", "sub_delay_reset", "sub_bigger", "sub_smaller",
                  "sub_up", "sub_down"):
            subm.addAction(a[k])
        subm.addSeparator()
        subm.addAction("Subtitle Style...", lambda: self._open_prefs_tab("Subtitles"))

        # Video
        vm = m.addMenu("Video")
        asp = vm.addMenu("Aspect Ratio")
        cur_asp = str(e.get("video-aspect-override", "-1"))
        for label, v in ASPECTS:
            act = asp.addAction(label, lambda v=v, label=label: self.set_aspect(v, label))
            act.setCheckable(True)
            act.setChecked(cur_asp == v or (v != "-1" and _same_ratio(cur_asp, v)))
        asp.addSeparator()
        asp.addAction(a["aspect_cycle"])
        crop = vm.addMenu("Crop")
        for label, r in CROPS:
            crop.addAction(label, lambda r=r, label=label: self.set_crop(r, label))
        crop.addSeparator()
        crop.addAction(a["fill_window"])
        zm = vm.addMenu("Zoom")
        for k in ("zoom_in", "zoom_out", "zoom_reset"):
            zm.addAction(a[k])
        tm = vm.addMenu("Rotate / Flip")
        for k in ("rotate_cw", "rotate_ccw", "flip_h", "flip_v"):
            tm.addAction(a[k])
        adj = vm.addMenu("Picture Adjustments")
        for k in ("brightness_up", "brightness_down", "contrast_up", "contrast_down",
                  "saturation_up", "saturation_down", "hue_up", "hue_down", "picture_reset"):
            adj.addAction(a[k])
        vm.addAction(a["deinterlace"])
        vm.addAction(a["hwdec_toggle"])
        vm.addSeparator()
        for k in ("screenshot", "screenshot_clean", "copy_frame"):
            vm.addAction(a[k])
        vm.addAction("Open Screenshot Folder", self._open_shot_dir)

        # View
        wm = m.addMenu("View")
        wm.addAction(a["fullscreen"])
        top = wm.addMenu("Always on Top")
        for mode, label in (("never", "Never"), ("always", "Always"), ("playing", "While Playing")):
            act = top.addAction(label, lambda mode=mode: self.set_on_top_mode(mode))
            act.setCheckable(True)
            act.setChecked(self.s["on_top"] == mode)
        ws = wm.addMenu("Window Size")
        for k in ("size_50", "size_100", "size_150", "size_200"):
            ws.addAction(a[k])
        wm.addAction(a["playlist_toggle"])
        wm.addAction(a["osd_info"])

        m.addSeparator()
        m.addAction(a["media_info"])
        m.addAction(a["preferences"])
        m.addAction(f"About {APP_NAME}", self.about)
        m.addSeparator()
        m.addAction(a["quit"])

        for k in ("stop", "close_file", "media_info", "open_subtitle", "open_audio", "screenshot",
                  "screenshot_clean", "copy_frame", "goto_time"):
            a[k].setEnabled(has)
        return m

    def _open_prefs_tab(self, tab):
        from .prefs import PreferencesDialog
        dlg = PreferencesDialog(self.s, self, start_tab=tab)
        if dlg.exec() == QDialog.Accepted:
            self.apply_settings()
            self.s.save()

    def _open_shot_dir(self):
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        d = os.path.expanduser(self.engine.get("screenshot-directory") or "")
        if d:
            os.makedirs(d, exist_ok=True)
            QDesktopServices.openUrl(QUrl.fromLocalFile(d))

    def about(self):
        import mpv as _mpv
        mpv_ver = self.engine.get("mpv-version", "?")
        QMessageBox.about(
            self, f"About {APP_NAME}",
            f"<b>{APP_NAME}</b> {__version__}<br>A keyboard-friendly video player for Linux.<br><br>"
            f"Playback: {mpv_ver} (libmpv) via python-mpv {getattr(_mpv, '__version__', '')}<br>"
            f"UI: Qt {qVersion()} (PySide6)")

    # ===================================================================================
    # engine events
    # ===================================================================================
    def _on_prop(self, name, v):
        c = self.controls
        if name == "pause":
            c.set_playing(bool(self.current) and not v)
            self.apply_on_top()
        elif name == "duration":
            c.seek.set_duration(v or 0)
            if v and self._resume_osd:
                self.engine.osd(f"Resumed at {fmt_time(self._resume_osd)}  (Home = from start)", 3000)
                self._resume_osd = None
            if v and self._queued_subs:
                for sp in self._queued_subs:
                    self.engine.command("sub-add", sp, "select")
                self._queued_subs = []
        elif name == "volume":
            if v is not None:
                self._set_volume_ui(v)
                self.s["volume"] = float(v)
        elif name == "mute":
            c.set_muted(bool(v))
            self.s["muted"] = bool(v)
        elif name == "eof-reached":
            if v:
                QTimer.singleShot(0, self._on_eof)
        elif name == "track-list":
            self.tracks = v or []
        elif name == "media-title":
            if v and self.current:
                self.setWindowTitle(f"{v} — {APP_NAME}")
        elif name == "video-params":
            if v and self.current:
                if self._fit_pending:
                    self._fit_pending = False
                    if self.s["fit_window_to_video"]:
                        QTimer.singleShot(0, self.fit_window)
                if self._thumb_for != self.current and self.s["thumbnails"]:
                    self._thumb_for = self.current
                    self.thumbs.set_file(self.current, v.get("dw") or v.get("w"), v.get("dh") or v.get("h"))
        elif name in ("speed", "hwdec-current"):
            self._update_info()
        elif name in ("ab-loop-a", "ab-loop-b"):
            c.seek.set_ab(self.engine.get("ab-loop-a"), self.engine.get("ab-loop-b"))
        elif name == "chapter-list":
            c.seek.set_chapters(v)
        elif name == "idle-active":
            if v:
                self._reset_ui()

    def _update_info(self):
        bits = []
        sp = self.engine.get("speed", 1.0)
        if abs(sp - 1.0) > 0.001:
            bits.append(f"{sp:.2f}x")
        hw = self.engine.get("hwdec-current")
        if self.current and hw and hw != "no":
            bits.append(f"HW: {hw}")
        self.controls.info_label.setText("   ".join(bits))

    def _on_eof(self):
        if not self.current or not self.engine.get("eof-reached"):
            return
        self.resume.remove(self.current)
        nxt = self.playlist.next_index(auto=True)
        if nxt is None:
            return
        if nxt == self.playlist.current_index() and self.s["repeat"] == "one":
            self._seek_to(0, True)
            self.engine.set("pause", False)
            return
        self.play_index(nxt)

    def _reset_ui(self):
        if self.current:
            return
        c = self.controls
        c.seek.set_duration(0)
        c.seek.set_position(0)
        c.seek.set_chapters([])
        c.seek.set_ab(None, None)
        c.time_label.setText("00:00 / 00:00")
        c.set_playing(False)
        self.thumbs.close()
        self._thumb_for = None
        self.setWindowTitle(APP_NAME)
        self._update_info()
        self.apply_on_top()

    def _update_position(self):
        if not self.current:
            return
        pos = self.engine.get("time-pos")
        dur = self.engine.get("duration")
        if pos is None:
            return
        self.controls.seek.set_position(pos)
        hours = (dur or 0) >= 3600
        if self._show_remaining and dur:
            txt = f"{fmt_time(pos - dur, hours)} / {fmt_time(dur, hours)}"
        else:
            txt = f"{fmt_time(pos, hours)} / {fmt_time(dur, hours) if dur else '--:--'}"
        self.controls.time_label.setText(txt)

    def _toggle_remaining(self):
        self._show_remaining = not self._show_remaining
        self._update_position()

    # -- seek-bar preview ---------------------------------------------------------------
    def _on_seek_hover(self, t, anchor):
        text = fmt_time(t, (self.controls.seek.duration or 0) >= 3600)
        chapters = self.engine.get("chapter-list", []) if self.controls.seek.chapters else []
        title = None
        for ch in chapters:
            if ch.get("time", 0) <= t:
                title = ch.get("title")
        if title:
            text = f"{text}  {title}"
        self._hover = (anchor, text)
        if self.thumbs.active:
            self.thumbs.request(t)
            self.popup.show_at(anchor, text)
        else:
            self.popup.clear_image()
            self.popup.show_at(anchor, text)

    def _on_seek_leave(self):
        self._hover = None
        self.thumbs.cancel()
        self.popup.hide()

    def _on_thumb(self, t, img):
        if self._hover is None:
            return
        anchor, text = self._hover
        w, h = self.thumbs.size
        self.popup.show_at(anchor, text, img, QSize(w, h))

    # ===================================================================================
    # input
    # ===================================================================================
    def eventFilter(self, obj, ev):
        if obj is self.video:
            t = ev.type()
            if t == QEvent.MouseButtonPress:
                b = ev.button()
                if b == Qt.LeftButton:
                    if self.s["click_to_pause"]:
                        self._click_timer.start()
                    return True
                if b == Qt.MiddleButton:
                    act = self.s["middle_click"]
                    if act == "mute":
                        self.engine.command("cycle", "mute")
                    elif act == "pause":
                        self.play_pause()
                    elif act == "fullscreen":
                        self.toggle_fullscreen()
                    return True
                if b == Qt.BackButton:
                    self.seek_rel(-self.s["seek_small"])
                    return True
                if b == Qt.ForwardButton:
                    self.seek_rel(self.s["seek_small"])
                    return True
            elif t == QEvent.MouseButtonDblClick and ev.button() == Qt.LeftButton:
                self._click_timer.stop()
                if not self.current and not self._pending_load:
                    self.open_file_dialog()
                elif self.s["double_click_fullscreen"]:
                    self.toggle_fullscreen()
                return True
        return super().eventFilter(obj, ev)

    def wheelEvent(self, ev):
        dy = ev.angleDelta().y()
        if not dy:
            return
        steps = dy / 120.0
        seek_mode = (self.s["wheel_action"] == "seek") != bool(ev.modifiers() & Qt.ControlModifier)
        if seek_mode:
            self.seek_rel(self.s["seek_small"] * (1 if steps > 0 else -1))
        else:
            self.change_volume(self.s["volume_step"] * steps)
        ev.accept()

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        paths = [u.toLocalFile() or u.toString() for u in e.mimeData().urls()]
        append = bool(e.modifiers() & (Qt.ShiftModifier | Qt.ControlModifier))
        self.open_targets(paths, append=append)
        self.activateWindow()

    def _update_ui_visibility(self):
        now = time.monotonic()
        pos = QCursor.pos()
        if pos != self._last_cursor:
            self._last_cursor = pos
            self._last_move = now
            if self._cursor_hidden:
                self.video.unsetCursor()
                self._cursor_hidden = False
        local = self.area.mapFromGlobal(pos)
        in_area = self.area.rect().contains(local) and self.isActiveWindow()
        idle = (now - self._last_move) * 1000 > int(self.s["hide_cursor_ms"])
        over_controls = self.controls.isVisible() and self.controls.geometry().contains(local)
        if self.isFullScreen():
            near_bottom = local.y() > self.area.height() - self.controls.sizeHint().height() - 50
            want = in_area and (over_controls or (near_bottom and not idle))
            if want != self.controls.isVisible():
                self.controls.setVisible(want)
                self.area.relayout()
        playing = bool(self.current) and not self.engine.get("pause", True)
        if in_area and idle and not over_controls and (playing or self.isFullScreen()):
            if not self._cursor_hidden:
                self.video.setCursor(Qt.BlankCursor)
                self._cursor_hidden = True

    # ===================================================================================
    # persistence / shutdown
    # ===================================================================================
    def _remember_position(self):
        if not self.current or not self.s["resume_playback"]:
            return
        pos = self.engine.get("time-pos")
        dur = self.engine.get("duration")
        if pos is None:
            return
        if self.engine.get("eof-reached") or (dur and pos > dur - 20):
            self.resume.remove(self.current)
        elif (dur is None or dur > 60) and pos > 15:
            self.resume.set(self.current, pos)
        else:
            self.resume.remove(self.current)

    def _periodic_save(self):
        self._remember_position()
        try:
            self.resume.save()
            self.s.save()
        except OSError:
            pass

    def receive_args(self, args):
        if args:
            self.open_targets(args)
        if self.isMinimized():
            self.showNormal()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, e):
        self._remember_position()
        self._pos_timer.stop()
        self._ui_timer.stop()
        self.popup.hide()
        self.thumbs.close()
        try:
            self.resume.save()
            self.s.save()
        except OSError:
            pass
        self.video.shutdown()
        self.engine.terminate()
        super().closeEvent(e)


def _ratio(v):
    try:
        if ":" in v:
            a, b = v.split(":")
            return float(a) / float(b)
        return float(v)
    except (ValueError, ZeroDivisionError):
        return None


def _same_ratio(a, b):
    ra, rb = _ratio(str(a)), _ratio(str(b))
    return ra is not None and rb is not None and ra > 0 and abs(ra - rb) < 0.01


def _human(n):
    if not n:
        return "?"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def _kbps(b):
    return f"{b / 1000:.0f} kb/s" if b else "?"

