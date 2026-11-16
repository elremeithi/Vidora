"""Entry point: environment setup, single-instance handoff, and the Qt event loop."""

import argparse
import getpass
import json
import os
import sys

from . import APP_ID, APP_NAME, __version__


def _prepare_environment(settings):
    if sys.platform.startswith("linux"):
        from .config import video_surface, wayland_session
        # Window embedding (--wid) only exists on X11, so run under XWayland in that mode.
        if (video_surface(settings) == "native" and wayland_session()
                and "QT_QPA_PLATFORM" not in os.environ):
            os.environ["QT_QPA_PLATFORM"] = "xcb"
    elif sys.platform == "win32":
        # Development convenience: find mpv-2.dll / libmpv-2.dll next to the project or via KINORA_MPV_DIR.
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        dirs = [os.environ.get("KINORA_MPV_DIR"), here]
        if getattr(sys, "frozen", False):  # packaged Kinora.exe: libmpv-2.dll ships next to it
            dirs = [os.path.dirname(sys.executable), getattr(sys, "_MEIPASS", None)] + dirs
        for d in filter(None, dirs):
            if os.path.isdir(d):
                os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")
                if hasattr(os, "add_dll_directory"):
                    os.add_dll_directory(d)


def _server_name():
    try:
        user = getpass.getuser()
    except Exception:
        user = "user"
    return f"{APP_ID}-{user}"


def _send_to_running(targets) -> bool:
    from PySide6.QtNetwork import QLocalSocket
    sock = QLocalSocket()
    sock.connectToServer(_server_name())
    if not sock.waitForConnected(300):
        return False
    sock.write(json.dumps(targets).encode("utf-8"))
    sock.flush()
    sock.waitForBytesWritten(1000)
    sock.disconnectFromServer()
    return True


def _start_server(window):
    from PySide6.QtNetwork import QLocalServer
    server = QLocalServer(window)
    name = _server_name()
    if not server.listen(name):
        QLocalServer.removeServer(name)  # stale socket from a crashed instance
        if not server.listen(name):
            return None

    def on_conn():
        sock = server.nextPendingConnection()
        buf = bytearray()

        def read():
            buf.extend(bytes(sock.readAll()))

        def done():
            read()
            try:
                targets = json.loads(buf.decode("utf-8") or "[]")
            except ValueError:
                targets = []
            window.receive_args(targets)
            sock.deleteLater()

        sock.readyRead.connect(read)
        sock.disconnected.connect(done)

    server.newConnection.connect(on_conn)
    return server


def _install_dark_title_bars(app):
    """Give every top-level window (main window, dialogs, message boxes) a dark caption."""
    from PySide6.QtCore import QEvent, QObject

    from .winassoc import dark_title_bar

    class _Hook(QObject):
        def eventFilter(self, obj, ev):
            if ev.type() == QEvent.Show and getattr(obj, "isWindow", lambda: False)() \
                    and not obj.property("_kinora_dark"):
                obj.setProperty("_kinora_dark", True)
                dark_title_bar(obj)
            return False

    app._dark_hook = _Hook(app)
    app.installEventFilter(app._dark_hook)


def main(argv=None):
    parser = argparse.ArgumentParser(prog=APP_ID, description=f"{APP_NAME} video player")
    parser.add_argument("targets", nargs="*", help="files, folders or URLs to play")
    parser.add_argument("--new-window", action="store_true", help="don't reuse a running window")
    parser.add_argument("--debug", action="store_true", help="verbose mpv log on stderr")
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    args = parser.parse_args(argv)

    from .config import ResumeStore, Settings
    from .util import normalize_target

    settings = Settings()
    _prepare_environment(settings)
    targets = [normalize_target(t) for t in args.targets]

    from PySide6.QtCore import Qt
    from PySide6.QtGui import QGuiApplication, QSurfaceFormat
    from PySide6.QtWidgets import QApplication, QMessageBox

    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    fmt = QSurfaceFormat.defaultFormat()
    fmt.setSwapInterval(1)
    QSurfaceFormat.setDefaultFormat(fmt)
    app = QApplication(sys.argv[:1])
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setDesktopFileName(APP_ID)
    app.setOrganizationName(APP_ID)

    if settings["single_instance"] and not args.new_window and _send_to_running(targets):
        return 0

    # libmpv refuses to start unless numbers are formatted the C way; Qt resets the locale.
    import locale
    locale.setlocale(locale.LC_NUMERIC, "C")

    from . import theme
    theme.apply(app)
    if sys.platform == "win32":
        _install_dark_title_bars(app)

    try:
        from .mainwindow import MainWindow  # imports python-mpv, which loads libmpv
        win = MainWindow(settings, ResumeStore(), debug=args.debug)
    except (OSError, ImportError) as e:
        QMessageBox.critical(None, APP_NAME,
                             "Could not load libmpv.\n\nInstall it with your package manager "
                             "(Debian/Ubuntu: libmpv2 or libmpv1, Fedora: mpv-libs, Arch: mpv) "
                             f"and try again.\n\nDetails: {e}")
        return 1

    if settings["single_instance"]:
        win._ipc_server = _start_server(win)
    win.show()
    if targets:
        win.open_targets(targets)
    return app.exec()
