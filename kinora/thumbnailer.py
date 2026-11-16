"""Seek-bar thumbnail previews.

A second, silent libmpv instance runs in encoding mode and writes one raw BGRA frame to a
temp file every time it is asked to seek (the same trick the popular "thumbfast" mpv
script uses). That keeps preview decoding completely separate from main playback.
"""

import os
import sys
import tempfile
import time
from collections import OrderedDict

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QImage

import mpv

from .util import is_url


class Thumbnailer(QObject):
    ready = Signal(float, QImage)

    def __init__(self, width=200, parent=None):
        super().__init__(parent)
        self.width = width
        self.size = (0, 0)
        self._mpv = None
        self._file = None
        self._out = os.path.join(tempfile.gettempdir(), f"kinora-thumb-{os.getpid()}.bgra")
        self._pending = None
        self._inflight = None
        self._stamp = None
        self._deadline = 0.0
        self._cache: OrderedDict[int, QImage] = OrderedDict()
        self._poll = QTimer(self, interval=20, timeout=self._check)

    @property
    def active(self):
        return self._mpv is not None

    def set_file(self, path, dw, dh):
        self.close()
        if not path or is_url(path) or not dw or not dh or not os.path.isfile(path):
            return
        w = self.width
        h = max(2, int(round(w * dh / dw / 2)) * 2)
        self.size = (w, h)
        try:
            os.remove(self._out)
        except OSError:
            pass
        try:
            self._mpv = mpv.MPV(
                config=False, idle="yes", pause=True, keep_open="always", ytdl=False,
                load_scripts=False, aid="no", sid="no", audio_file_auto="no",
                sub_auto="no", hwdec="no", hr_seek="no", vd_lavc_skiploopfilter="all",
                vd_lavc_fast=True, vd_lavc_threads=2, demuxer_readahead_secs=0,
                vf=f"scale=w={w}:h={h},format=fmt=bgra",
                ovc="rawvideo", of="image2", ofopts="update=1", o=self._out,
            )
            self._mpv.command("loadfile", path)
        except Exception as e:
            sys.stderr.write(f"thumbnails disabled: {e}\n")
            self._mpv = None
            return
        self._file = path

    def close(self):
        self._poll.stop()
        self._pending = self._inflight = None
        self._cache.clear()
        if self._mpv is not None:
            m, self._mpv = self._mpv, None
            try:
                m.terminate()
            except Exception:
                pass
        self._file = None

    def cancel(self):
        self._pending = None

    def request(self, t: float):
        if self._mpv is None:
            return
        key = int(t)
        img = self._cache.get(key)
        if img is not None:
            self.ready.emit(t, img)
            return
        self._pending = t
        if self._inflight is None:
            self._start_next()

    def _stat(self):
        try:
            st = os.stat(self._out)
            return (st.st_mtime_ns, st.st_size)
        except OSError:
            return None

    def _start_next(self):
        t, self._pending = self._pending, None
        if t is None or self._mpv is None:
            return
        self._inflight = t
        self._stamp = self._stat()
        self._deadline = time.monotonic() + 2.0
        try:
            self._mpv.command_async("seek", f"{t:.2f}", "absolute+keyframes")
        except Exception:
            try:
                self._mpv.command("seek", f"{t:.2f}", "absolute+keyframes")
            except Exception:
                pass
        self._poll.start()

    def _check(self):
        w, h = self.size
        st = self._stat()
        done = False
        if st and st != self._stamp and st[1] == w * h * 4:
            try:
                with open(self._out, "rb") as f:
                    data = f.read()
            except OSError:
                data = b""
            if len(data) == w * h * 4:
                img = QImage(data, w, h, w * 4, QImage.Format_RGB32).copy()
                key = int(self._inflight)
                self._cache[key] = img
                if len(self._cache) > 300:
                    self._cache.popitem(last=False)
                self.ready.emit(self._inflight, img)
                done = True
        if not done and time.monotonic() > self._deadline:
            done = True
        if done:
            self._inflight = None
            if self._pending is not None:
                self._start_next()
            else:
                self._poll.stop()
