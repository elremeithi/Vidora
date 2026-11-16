"""Control-bar icons drawn with QPainter so the app ships no image assets."""

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap

_cache = {}


def icon(name: str, color: str = "#E6E6E6") -> QIcon:
    key = (name, color)
    if key in _cache:
        return _cache[key]
    ic = QIcon()
    for c, mode in ((color, QIcon.Normal), ("#FFFFFF", QIcon.Active), ("#6A6A6A", QIcon.Disabled)):
        ic.addPixmap(_draw(name, QColor(c)), mode)
    _cache[key] = ic
    return ic


def _draw(name, color: QColor, size=64) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(color)
    p.setPen(Qt.NoPen)
    s = size / 64.0
    p.scale(s, s)

    def poly(*pts):
        path = QPainterPath(QPointF(*pts[0]))
        for pt in pts[1:]:
            path.lineTo(QPointF(*pt))
        path.closeSubpath()
        p.drawPath(path)

    stroke = QPen(color, 5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)

    if name == "play":
        poly((20, 12), (52, 32), (20, 52))
    elif name == "pause":
        p.drawRoundedRect(QRectF(16, 12, 11, 40), 2, 2)
        p.drawRoundedRect(QRectF(37, 12, 11, 40), 2, 2)
    elif name == "stop":
        p.drawRoundedRect(QRectF(16, 16, 32, 32), 3, 3)
    elif name == "prev":
        p.drawRect(QRectF(12, 14, 7, 36))
        poly((50, 14), (22, 32), (50, 50))
    elif name == "next":
        p.drawRect(QRectF(45, 14, 7, 36))
        poly((14, 14), (42, 32), (14, 50))
    elif name == "open":
        poly((32, 12), (52, 34), (12, 34))
        p.drawRect(QRectF(12, 42, 40, 7))
    elif name == "fullscreen":
        p.setBrush(Qt.NoBrush)
        p.setPen(stroke)
        for (x, y, dx, dy) in ((12, 12, 1, 1), (52, 12, -1, 1), (12, 52, 1, -1), (52, 52, -1, -1)):
            p.drawPolyline([QPointF(x, y + 12 * dy), QPointF(x, y), QPointF(x + 12 * dx, y)])
    elif name == "unfullscreen":
        p.setBrush(Qt.NoBrush)
        p.setPen(stroke)
        for (x, y, dx, dy) in ((26, 26, -1, -1), (38, 26, 1, -1), (26, 38, -1, 1), (38, 38, 1, 1)):
            p.drawPolyline([QPointF(x, y + 12 * dy), QPointF(x, y), QPointF(x + 12 * dx, y)])
    elif name == "playlist":
        for y in (16, 30, 44):
            p.drawRoundedRect(QRectF(10, y, 30, 5), 2, 2)
        poly((44, 34), (56, 42), (44, 50))
    elif name in ("volume", "mute"):
        poly((10, 24), (20, 24), (32, 12), (32, 52), (20, 40), (10, 40))
        p.setBrush(Qt.NoBrush)
        p.setPen(stroke)
        if name == "volume":
            p.drawArc(QRectF(28, 22, 16, 20), -50 * 16, 100 * 16)
            p.drawArc(QRectF(28, 14, 26, 36), -50 * 16, 100 * 16)
        else:
            p.drawLine(QPointF(40, 24), QPointF(54, 40))
            p.drawLine(QPointF(54, 24), QPointF(40, 40))
    elif name == "menu":
        for y in (16, 30, 44):
            p.drawRoundedRect(QRectF(12, y, 40, 5), 2, 2)
    elif name == "repeat":
        p.setBrush(Qt.NoBrush)
        p.setPen(stroke)
        p.drawArc(QRectF(12, 14, 40, 36), 30 * 16, 300 * 16)
        p.setPen(Qt.NoPen)
        p.setBrush(color)
        poly((44, 8), (56, 20), (42, 24))
    elif name == "shuffle":
        p.setBrush(Qt.NoBrush)
        p.setPen(stroke)
        p.drawLine(QPointF(10, 18), QPointF(44, 46))
        p.drawLine(QPointF(10, 46), QPointF(44, 18))
        p.setPen(Qt.NoPen)
        p.setBrush(color)
        poly((42, 10), (56, 18), (42, 26))
        poly((42, 38), (56, 46), (42, 54))
    p.end()
    return pm


def app_icon() -> QIcon:
    """The window icon: a rounded tile with a play mark and an offset ring."""
    ic = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        pm = QPixmap(size, size)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.scale(size / 64.0, size / 64.0)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#1F2A30"))
        p.drawRoundedRect(QRectF(2, 2, 60, 60), 14, 14)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor("#2BB3A3"), 5))
        p.drawEllipse(QRectF(12, 12, 40, 40))
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#F2F2F2"))
        path = QPainterPath(QPointF(27, 22))
        path.lineTo(QPointF(44, 32))
        path.lineTo(QPointF(27, 42))
        path.closeSubpath()
        p.drawPath(path)
        p.end()
        ic.addPixmap(pm)
    return ic
