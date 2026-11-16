"""Thin Qt-friendly wrapper around a libmpv handle (python-mpv).

mpv calls property observers on its own thread; everything is forwarded to the Qt main
thread through the ``prop_changed`` signal so the UI never touches widgets off-thread.
"""

import sys

from PySide6.QtCore import QObject, Signal

import mpv

OBSERVED = [
    "pause", "duration", "volume", "mute", "eof-reached", "track-list", "media-title", "path",
    "video-params", "speed", "ab-loop-a", "ab-loop-b", "chapter-list", "idle-active",
    "sub-delay", "audio-delay", "hwdec-current", "seekable",
]


class Engine(QObject):
    prop_changed = Signal(str, object)

    def __init__(self, settings, wid=None, debug=False, parent=None):
        super().__init__(parent)
        self.settings = settings
        pre_init = dict(
            idle="yes",
            keep_open="yes",
            input_default_bindings=False,
            input_vo_keyboard=False,
            input_cursor=False,
            cursor_autohide="no",
            config=bool(settings["load_mpv_config"]),
            ytdl=True,
            osd_level=1,
            osd_duration=1500,
            osd_font_size=32,
            osd_border_size=2,
            hwdec=settings["hwdec"],
        )
        if wid is None:
            pre_init["vo"] = "libmpv"
        else:
            pre_init["wid"] = str(int(wid))
        self.mpv = mpv.MPV(log_handler=self._on_log, loglevel="v" if debug else "warn", **pre_init)
        self._debug = debug
        for name in OBSERVED:
            self.mpv.observe_property(name, self._on_prop)
        self.apply_settings(settings, initial=True)

    # -- plumbing -------------------------------------------------------------------------
    def _on_prop(self, name, value):
        self.prop_changed.emit(name, value)

    def _on_log(self, level, component, message):
        if self._debug or level in ("fatal", "error"):
            sys.stderr.write(f"[mpv/{component}] {level}: {message.rstrip()}\n")

    # Note: python-mpv's mpv["x"] reads/writes "options/x", not the live property, and its
    # attribute API silently swallows some errors, so talk to the property layer directly.
    def get(self, name, default=None):
        try:
            v = self.mpv._get_property(name, mpv.lazy_decoder)
        except Exception:
            return default
        return default if v is None else v

    def set(self, name, value) -> bool:
        try:
            self.mpv._set_property(name, value)
            return True
        except Exception as e:
            if self._debug:
                sys.stderr.write(f"set {name}={value!r} failed: {e}\n")
            return False

    def command(self, *args) -> bool:
        try:
            self.mpv.command(*args)
            return True
        except Exception as e:
            if self._debug:
                sys.stderr.write(f"command {args!r} failed: {e}\n")
            return False

    def osd(self, text: str, ms: int = 1500):
        self.command("show-text", text, ms)

    def terminate(self):
        try:
            self.mpv.terminate()
        except Exception:
            pass

    # -- settings -------------------------------------------------------------------------
    def apply_settings(self, s, initial=False):
        props = {
            "volume-max": float(s["volume_max"]),
            "audio-pitch-correction": bool(s["pitch_correction"]),
            "hr-seek": "yes" if s["precise_seek"] else "default",
            "hwdec": s["hwdec"],
            "sub-auto": s["sub_auto"],
            "slang": s["sub_langs"] or "",
            "alang": s["audio_langs"] or "",
            "sub-font": s["sub_font"],
            "sub-font-size": float(s["sub_font_size"]),
            "sub-color": s["sub_color"],
            "sub-border-color": s["sub_border_color"],
            "sub-border-size": float(s["sub_border_size"]),
            "sub-bold": bool(s["sub_bold"]),
            "sub-pos": int(s["sub_pos"]),
            "sub-scale": float(s["sub_scale"]),
            "sub-ass-override": "force" if s["sub_override_ass"] else "scale",
            "sub-codepage": s["sub_codepage"] or "auto",
            "screenshot-format": s["screenshot_format"],
            "screenshot-template": "%F-%wH.%wM.%wS.%wT-%n",
            "screenshot-directory": s["screenshot_dir"] or _default_shot_dir(),
        }
        if initial:
            props["deinterlace"] = bool(s["deinterlace"])
            if s["remember_volume"]:
                props["volume"] = float(s["volume"])
                props["mute"] = bool(s["muted"])
        for k, v in props.items():
            self.set(k, v)
        self.set_normalize(bool(s["normalize"]))

    def set_normalize(self, on: bool):
        self.command("af", "remove", "@norm")
        if on:
            self.command("af", "add", "@norm:lavfi=[dynaudnorm=f=250:g=15]")


def _default_shot_dir():
    import os
    from .config import pictures_dir
    d = pictures_dir()
    os.makedirs(d, exist_ok=True)
    return d
