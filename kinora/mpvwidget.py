"""Video surfaces.

``MpvGLWidget`` uses libmpv's OpenGL render API inside a QOpenGLWidget. It works the
same on X11 and Wayland, lets Qt receive every mouse event and allows Qt widgets
(the fullscreen control bar) to be drawn on top of the video.

``NativeVideoWidget`` is the fallback: mpv draws into a native child window (``--wid``).
On Wayland this requires XWayland, which app.py arranges by forcing QT_QPA_PLATFORM=xcb.
"""

import ctypes
import ctypes.util
import sys

from PySide6.QtCore import QByteArray, Qt, Signal
from PySide6.QtGui import QOpenGLContext
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtWidgets import QWidget

import mpv

_fallback_loader = None


def _native_proc_loader():
    """Return a function name(bytes)->int using the platform GL loader (used only if Qt's fails)."""
    if sys.platform == "win32":
        gl = ctypes.WinDLL("opengl32")
        wgl = gl.wglGetProcAddress
        wgl.restype = ctypes.c_void_p
        wgl.argtypes = [ctypes.c_char_p]
        k32 = ctypes.WinDLL("kernel32")
        gpa = k32.GetProcAddress
        gpa.restype = ctypes.c_void_p
        gpa.argtypes = [ctypes.c_void_p, ctypes.c_char_p]

        def load(name):
            a = wgl(name)
            if a in (None, 0, 1, 2, 3, -1):
                a = gpa(gl._handle, name)
            return a or 0
        return load
    for libname, fn in (("EGL", "eglGetProcAddress"), ("GL", "glXGetProcAddressARB")):
        path = ctypes.util.find_library(libname)
        if not path:
            continue
        try:
            lib = ctypes.CDLL(path)
            f = getattr(lib, fn)
        except (OSError, AttributeError):
            continue
        f.restype = ctypes.c_void_p
        f.argtypes = [ctypes.c_char_p]
        return lambda name, f=f: f(name) or 0
    return lambda name: 0


def _get_proc_address(_ctx, name):
    global _fallback_loader
    glctx = QOpenGLContext.currentContext()
    addr = 0
    if glctx is not None:
        try:
            addr = int(glctx.getProcAddress(QByteArray(name)) or 0)
        except Exception:
            addr = 0
    if not addr:
        if _fallback_loader is None:
            _fallback_loader = _native_proc_loader()
        addr = _fallback_loader(name)
    return addr


class MpvGLWidget(QOpenGLWidget):
    _frame_ready = Signal()
    ready = Signal(bool)  # emitted after the mpv renderer exists; True if it was re-created
    is_native = False

    def __init__(self, player: "mpv.MPV", parent=None):
        super().__init__(parent)
        self.player = player
        self.ctx = None
        self._proc_fn = None
        self._created_once = False
        self._frame_ready.connect(self.update, Qt.QueuedConnection)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setContextMenuPolicy(Qt.CustomContextMenu)

    def initializeGL(self):
        # Qt may recreate the GL context (e.g. when the window is re-parented); release
        # mpv's renderer first so a fresh one can be created on the new context.
        self.context().aboutToBeDestroyed.connect(self._free_ctx, Qt.DirectConnection)
        self._free_ctx()
        self._proc_fn = mpv.MpvGlGetProcAddressFn(_get_proc_address)
        self.ctx = mpv.MpvRenderContext(
            self.player, "opengl", opengl_init_params={"get_proc_address": self._proc_fn})
        self.ctx.update_cb = self._on_mpv_update
        self.ready.emit(self._created_once)
        self._created_once = True

    def _on_mpv_update(self):
        # Called on an mpv thread: only signal, never render here.
        self._frame_ready.emit()

    def paintGL(self):
        if self.ctx is None:
            return
        r = self.devicePixelRatioF()
        w, h = int(self.width() * r), int(self.height() * r)
        self.ctx.render(flip_y=True, opengl_fbo={"w": w, "h": h, "fbo": self.defaultFramebufferObject()})

    def _free_ctx(self):
        if self.ctx is not None:
            self.makeCurrent()
            try:
                self.ctx.free()
            finally:
                self.ctx = None
                self.doneCurrent()

    def shutdown(self):
        self._free_ctx()


class NativeVideoWidget(QWidget):
    is_native = True

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_DontCreateNativeAncestors)
        self.setAttribute(Qt.WA_NativeWindow)
        self.setAttribute(Qt.WA_StyledBackground)
        self.setStyleSheet("background: black;")
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setContextMenuPolicy(Qt.CustomContextMenu)

    def shutdown(self):
        pass
