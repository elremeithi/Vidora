"""Settings (JSON) and per-file resume positions, stored under the XDG config dir."""

import hashlib
import json
import os
import sys
import time
from pathlib import Path

from . import APP_ID


def config_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home())
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    d = base / APP_ID
    legacy = base / "kinora"  # settings folder from before the app was renamed to Vidora
    if not d.exists() and legacy.is_dir():
        import shutil
        try:
            shutil.copytree(legacy, d)
        except OSError:
            pass
    d.mkdir(parents=True, exist_ok=True)
    return d


def pictures_dir() -> str:
    d = None
    if sys.platform.startswith("linux"):
        try:
            import subprocess
            d = subprocess.run(["xdg-user-dir", "PICTURES"], capture_output=True, text=True,
                               timeout=2).stdout.strip() or None
        except Exception:
            d = None
    return str(Path(d or Path.home() / "Pictures") / "Vidora")


DEFAULTS = {
    # general
    "resume_playback": True,
    "remember_volume": True,
    "volume": 100.0,
    "muted": False,
    "auto_add_folder": True,
    "single_instance": True,
    "fit_window_to_video": True,
    "max_window_percent": 80,
    "on_top": "never",  # never | always | playing
    "load_mpv_config": False,
    "video_surface": "auto",  # auto | opengl (libmpv render API) | native (mpv draws in its own window)
    "recent": [],
    "max_recent": 20,
    # mouse
    "click_to_pause": True,
    "double_click_fullscreen": True,
    "wheel_action": "volume",  # volume | seek
    "middle_click": "mute",  # mute | pause | fullscreen | none
    "hide_cursor_ms": 2000,
    # playback
    "seek_fine": 1,
    "seek_small": 5,
    "seek_medium": 30,
    "seek_large": 60,
    "precise_seek": False,
    "volume_step": 5,
    "speed_step": 0.1,
    "repeat": "off",  # off | one | all
    "shuffle": False,
    "hwdec": "auto-safe",
    "thumbnails": True,
    # video
    "deinterlace": False,
    "screenshot_dir": "",
    "screenshot_format": "png",  # png | jpg | webp
    "screenshot_with_subs": True,
    # audio
    "audio_langs": "",
    "volume_max": 200,
    "pitch_correction": True,
    "normalize": False,
    # subtitles
    "sub_auto": "fuzzy",
    "sub_langs": "eng,en",
    "sub_font": "Sans",
    "sub_font_size": 44,
    "sub_color": "#FFFFFF",
    "sub_border_color": "#000000",
    "sub_border_size": 3.0,
    "sub_bold": False,
    "sub_pos": 100,
    "sub_scale": 1.0,
    "sub_override_ass": False,
    "sub_codepage": "auto",
    # keyboard overrides: action id -> list of portable key strings
    "keys": {},
}


def wayland_session() -> bool:
    return sys.platform.startswith("linux") and bool(
        os.environ.get("WAYLAND_DISPLAY") or os.environ.get("XDG_SESSION_TYPE") == "wayland")


def video_surface(settings) -> str:
    """Resolve "auto": native window embedding on X11 (most robust there, full hwdec);
    the OpenGL render API on Wayland (embedding needs X11) and Windows (fullscreen overlay)."""
    v = settings["video_surface"]
    if v in ("opengl", "native"):
        return v
    if sys.platform.startswith("linux") and not wayland_session():
        return "native"
    return "opengl"


class Settings:
    def __init__(self, path: Path | None = None):
        self.path = path or config_dir() / "settings.json"
        self.data = dict(DEFAULTS)
        try:
            with open(self.path, encoding="utf-8") as f:
                stored = json.load(f)
            if isinstance(stored, dict):
                self.data.update({k: v for k, v in stored.items() if k in DEFAULTS})
        except (OSError, ValueError):
            pass

    def __getitem__(self, key):
        return self.data.get(key, DEFAULTS.get(key))

    def __setitem__(self, key, value):
        self.data[key] = value

    def save(self):
        tmp = self.path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, self.path)

    def add_recent(self, target: str):
        rec = [r for r in self["recent"] if r != target]
        rec.insert(0, target)
        self["recent"] = rec[: int(self["max_recent"])]


class ResumeStore:
    """Remembers where each file was left. Keyed by a hash of the path/URL."""

    LIMIT = 1000

    def __init__(self, path: Path | None = None):
        self.path = path or config_dir() / "resume.json"
        self.data: dict = {}
        try:
            with open(self.path, encoding="utf-8") as f:
                self.data = json.load(f)
        except (OSError, ValueError):
            self.data = {}

    @staticmethod
    def _key(target: str) -> str:
        return hashlib.sha1(target.encode("utf-8", "surrogatepass")).hexdigest()

    def get(self, target: str):
        e = self.data.get(self._key(target))
        return e.get("pos") if isinstance(e, dict) else None

    def set(self, target: str, pos: float):
        self.data[self._key(target)] = {"pos": round(pos, 2), "ts": int(time.time())}
        if len(self.data) > self.LIMIT:
            keep = sorted(self.data.items(), key=lambda kv: kv[1].get("ts", 0), reverse=True)
            self.data = dict(keep[: self.LIMIT])

    def remove(self, target: str):
        self.data.pop(self._key(target), None)

    def save(self):
        tmp = self.path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f)
        os.replace(tmp, self.path)
