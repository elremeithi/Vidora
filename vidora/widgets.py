"""Control bar, seek bar with thumbnail preview, and the volume slider."""

from PySide6.QtCore import QPoint, QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QSizePolicy, QSlider, QToolButton,
                               QVBoxLayout, QWidget)

from . import theme
from .icons import icon
from .util import fmt_time


class SeekBar(QWidget):
    """Click-anywhere seek bar with chapter ticks, A-B markers and hover preview signals."""

    seek_requested = Signal(float, bool)  # seconds, exact
    hovered = Signal(float, QPoint)  # seconds, global position of the hover point (on the bar)
    hover_left = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.duration = 0.0
        self.position = 0.0
        self.chapters: list[float] = []
        self.ab = (None, None)
        self._dragging = False
        self._hover_x = None
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.NoFocus)
        self.setMinimumHeight(18)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setCursor(Qt.PointingHandCursor)

    def sizeHint(self):
        return QSize(400, 18)

    def set_duration(self, d):
        self.duration = float(d or 0)
        self.update()

    def set_position(self, p):
        if not self._dragging:
            self.position = float(p or 0)
            self.update()

    def set_chapters(self, chapters):
        self.chapters = [c.get("time", 0) for c in (chapters or []) if isinstance(c, dict)]
        self.update()

    def set_ab(self, a, b):
        self.ab = (a if isinstance(a, (int, float)) else None, b if isinstance(b, (int, float)) else None)
        self.update()

    def _groove(self):
        m = 8
        return QRectF(m, self.height() / 2 - 2.5, self.width() - 2 * m, 5)

    def _x_to_time(self, x):
        g = self._groove()
        if self.duration <= 0 or g.width() <= 0:
            return 0.0
        f = min(1.0, max(0.0, (x - g.left()) / g.width()))
        return f * self.duration

    def _time_to_x(self, t):
        g = self._groove()
        if self.duration <= 0:
            return g.left()
        return g.left() + g.width() * min(1.0, max(0.0, t / self.duration))

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        g = self._groove()
        hover = self._hover_x is not None and self.duration > 0
        if hover:
            g = g.adjusted(0, -1, 0, 1)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 45))
        p.drawRoundedRect(g, 3, 3)
        a, b = self.ab
        if a is not None and self.duration > 0:
            xa = self._time_to_x(a)
            xb = self._time_to_x(b) if b is not None else xa + 2
            p.setBrush(QColor(255, 196, 0, 90))
            p.drawRect(QRectF(xa, g.top() - 3, max(2, xb - xa), g.height() + 6))
        if self.duration > 0:
            x = self._time_to_x(self.position)
            p.setBrush(QColor(theme.ACCENT))
            p.drawRoundedRect(QRectF(g.left(), g.top(), x - g.left(), g.height()), 3, 3)
            p.setBrush(QColor(0, 0, 0, 160))
            for c in self.chapters:
                cx = self._time_to_x(c)
                if g.left() + 2 < cx < g.right() - 2:
                    p.drawRect(QRectF(cx - 1, g.top(), 2, g.height()))
            if hover:
                p.setBrush(QColor(255, 255, 255, 120))
                p.drawRect(QRectF(self._hover_x - 0.5, g.top() - 2, 1, g.height() + 4))
            p.setBrush(QColor(theme.TEXT))
            r = 6.5 if (hover or self._dragging) else 5
            p.drawEllipse(QPointF(x, g.center().y()), r, r)
        p.end()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and self.duration > 0:
            self._dragging = True
            self.position = self._x_to_time(e.position().x())
            self.seek_requested.emit(self.position, False)
            self.update()

    def mouseMoveEvent(self, e):
        x = e.position().x()
        self._hover_x = x
        if self.duration > 0:
            t = self._x_to_time(x)
            g = self._groove()
            self.hovered.emit(t, self.mapToGlobal(QPoint(int(min(max(x, g.left()), g.right())), 0)))
            if self._dragging:
                self.position = t
                self.seek_requested.emit(t, False)
        self.update()

    def mouseReleaseEvent(self, e):
        if self._dragging and e.button() == Qt.LeftButton:
            self._dragging = False
            self.position = self._x_to_time(e.position().x())
            self.seek_requested.emit(self.position, True)
            self.update()

    def leaveEvent(self, _):
        self._hover_x = None
        self.hover_left.emit()
        self.update()

    def wheelEvent(self, e):
        e.ignore()  # let the window handle wheel (volume)


class ClickableLabel(QLabel):
    clicked = Signal()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.clicked.emit()


class ThumbPopup(QWidget):
    """Preview frame + hovered time, drawn as a child of the video area.

    Being a child widget (not a tooltip window) keeps positioning reliable on Wayland,
    where clients cannot place their own top-level windows.
    """

    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.image = None
        self.text = ""
        self.img_size = QSize(0, 0)
        self.hide()

    def show_at(self, anchor: QPoint, text: str, image=None, img_size: QSize | None = None):
        """``anchor`` is the global position of the hovered point on the seek bar."""
        self.text = text
        if image is not None:
            self.image = image
        if img_size is not None:
            self.img_size = img_size
        has_img = self.image is not None and self.img_size.width() > 0
        fm = self.fontMetrics()
        w = max(self.img_size.width() + 4 if has_img else 0, fm.horizontalAdvance(text) + 20, 70)
        h = (self.img_size.height() + 4 if has_img else 0) + 22
        self.resize(w, h)
        local = self.parentWidget().mapFromGlobal(anchor)
        pw = self.parentWidget().width()
        x = max(0, min(local.x() - w // 2, pw - w))
        y = max(0, local.y() - h - 8)
        self.move(x, y)
        if not self.isVisible():
            self.show()
        self.raise_()
        self.update()

    def clear_image(self):
        self.image = None
        self.img_size = QSize(0, 0)

    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(theme.SURFACE))
        p.setPen(QPen(QColor(theme.BORDER)))
        p.drawRect(self.rect().adjusted(0, 0, -1, -1))
        top = 2
        if self.image is not None and self.img_size.width() > 0:
            iw, ih = self.img_size.width(), self.img_size.height()
            p.drawImage(QRectF((self.width() - iw) / 2, 2, iw, ih), self.image)
            top = ih + 2
        p.setPen(QColor(theme.TEXT))
        f = QFont(self.font())
        f.setBold(True)
        p.setFont(f)
        p.drawText(QRectF(0, top, self.width(), self.height() - top), Qt.AlignCenter, self.text)
        p.end()


class VolumeSlider(QSlider):
    def __init__(self, parent=None):
        super().__init__(Qt.Horizontal, parent)
        self.setFocusPolicy(Qt.NoFocus)
        self.setRange(0, 100)
        self.setFixedWidth(90)
        self.setPageStep(5)

    def mousePressEvent(self, e):
        # jump straight to the clicked value
        if e.button() == Qt.LeftButton and self.width() > 0:
            v = self.minimum() + (self.maximum() - self.minimum()) * e.position().x() / self.width()
            self.setValue(int(round(v)))
        super().mousePressEvent(e)


def _btn(name, tip):
    b = QToolButton()
    b.setIcon(icon(name))
    b.setIconSize(QSize(20, 20))
    b.setToolTip(tip)
    b.setFocusPolicy(Qt.NoFocus)
    b.setAutoRaise(True)
    return b


class ControlBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.translucent = False
        self.setFocusPolicy(Qt.NoFocus)
        self.setAttribute(Qt.WA_StyledBackground, False)
        self.seek = SeekBar()

        self.btn_menu = _btn("menu", "Menu (right-click the video too)")
        self.btn_open = _btn("open", "Open file")
        self.btn_prev = _btn("prev", "Previous file")
        self.btn_play = _btn("play", "Play / Pause")
        self.btn_stop = _btn("stop", "Stop")
        self.btn_next = _btn("next", "Next file")
        self.time_label = ClickableLabel("00:00 / 00:00")
        self.time_label.setStyleSheet(f"color: {theme.TEXT}; padding: 0 6px;")
        self.time_label.setCursor(Qt.PointingHandCursor)
        self.time_label.setToolTip("Click to toggle remaining time")
        self.info_label = QLabel("")
        self.info_label.setStyleSheet(f"color: {theme.SUBTLE}; padding: 0 6px;")
        self.btn_playlist = _btn("playlist", "Playlist")
        self.btn_playlist.setCheckable(True)
        self.btn_full = _btn("fullscreen", "Fullscreen")
        self.btn_mute = _btn("volume", "Mute")
        self.volume = VolumeSlider()
        self.vol_label = QLabel("100%")
        self.vol_label.setMinimumWidth(42)
        self.vol_label.setStyleSheet(f"color: {theme.SUBTLE};")

        row = QHBoxLayout()
        row.setContentsMargins(6, 0, 8, 4)
        row.setSpacing(2)
        for w in (self.btn_menu, self.btn_open, self.btn_prev, self.btn_play, self.btn_stop,
                  self.btn_next, self.time_label):
            row.addWidget(w)
        row.addStretch(1)
        row.addWidget(self.info_label)
        for w in (self.btn_playlist, self.btn_full, self.btn_mute, self.volume, self.vol_label):
            row.addWidget(w)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 4, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self.seek)
        lay.addLayout(row)

    def set_translucent(self, on):
        self.translucent = on
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(20, 20, 20, 215) if self.translucent else QColor(theme.BG))
        p.end()

    def set_playing(self, playing: bool):
        self.btn_play.setIcon(icon("pause" if playing else "play"))

    def set_fullscreen(self, fs: bool):
        self.btn_full.setIcon(icon("unfullscreen" if fs else "fullscreen"))

    def set_muted(self, muted: bool):
        self.btn_mute.setIcon(icon("mute" if muted else "volume"))
