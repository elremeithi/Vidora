"""Small helpers shared across the app: file types, sorting, time formatting."""

import os
import re
from pathlib import Path

VIDEO_EXTS = {
    ".3g2", ".3gp", ".amv", ".asf", ".avi", ".divx", ".dv", ".f4v", ".flv", ".h264", ".hevc",
    ".ifo", ".m1v", ".m2t", ".m2ts", ".m2v", ".m4v", ".mkv", ".mov", ".mp2v", ".mp4", ".mpe",
    ".mpeg", ".mpg", ".mpv", ".mts", ".mxf", ".nsv", ".nut", ".ogm", ".ogv", ".qt", ".rm",
    ".rmvb", ".tod", ".trp", ".ts", ".vob", ".webm", ".wmv", ".wtv", ".y4m", ".av1", ".ivf",
}
AUDIO_EXTS = {
    ".aac", ".ac3", ".aiff", ".alac", ".ape", ".au", ".dts", ".eac3", ".flac", ".m4a", ".m4b",
    ".mka", ".mp1", ".mp2", ".mp3", ".mpc", ".oga", ".ogg", ".opus", ".ra", ".shn", ".spx",
    ".tak", ".thd", ".tta", ".wav", ".wma", ".wv",
}
SUB_EXTS = {".srt", ".ass", ".ssa", ".sub", ".idx", ".vtt", ".sup", ".smi", ".sami", ".lrc", ".mks"}
MEDIA_EXTS = VIDEO_EXTS | AUDIO_EXTS

_URL_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://")


def is_url(s: str) -> bool:
    return bool(s) and _URL_RE.match(s) is not None and not s.lower().startswith("file://")


def ext_of(path: str) -> str:
    return os.path.splitext(path)[1].lower()


def is_media(path: str) -> bool:
    return ext_of(path) in MEDIA_EXTS


def is_subtitle(path: str) -> bool:
    return ext_of(path) in SUB_EXTS


def natural_key(s: str):
    return [int(t) if t.isdigit() else t.casefold() for t in re.split(r"(\d+)", s)]


def media_in_folder(folder: str, recursive: bool = False) -> list[str]:
    """Media files in a folder, naturally sorted (episode 2 before episode 10)."""
    out = []
    try:
        if recursive:
            for root, dirs, files in os.walk(folder):
                dirs.sort(key=natural_key)
                for f in sorted(files, key=natural_key):
                    if is_media(f):
                        out.append(os.path.join(root, f))
        else:
            for f in sorted(os.listdir(folder), key=natural_key):
                p = os.path.join(folder, f)
                if is_media(f) and os.path.isfile(p):
                    out.append(p)
    except OSError:
        pass
    return out


def normalize_target(s: str) -> str:
    """Absolute path for local files, untouched for URLs."""
    if s.lower().startswith("file://"):
        from urllib.parse import unquote, urlparse
        s = unquote(urlparse(s).path)
        if os.name == "nt" and re.match(r"^/[A-Za-z]:", s):
            s = s[1:]
    if is_url(s):
        return s
    return str(Path(s).expanduser().resolve())


def display_name(target: str) -> str:
    if is_url(target):
        return target
    return os.path.basename(target) or target


def fmt_time(sec, hours: bool | None = None) -> str:
    if sec is None:
        sec = 0
    neg = sec < 0
    sec = int(abs(sec))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    if hours is None:
        hours = h > 0
    txt = f"{h}:{m:02d}:{s:02d}" if hours else f"{m:02d}:{s:02d}"
    return "-" + txt if neg else txt
