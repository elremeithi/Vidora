"""Playlist dock: drag to reorder, drop files in, double-click to play."""

import os
import random

from PySide6.QtCore import QEvent, QSize, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import (QAbstractItemView, QHBoxLayout, QListWidget, QListWidgetItem,
                               QMenu, QToolButton, QVBoxLayout, QWidget)

from .icons import icon
from .util import display_name, is_media, is_url, media_in_folder, natural_key, normalize_target

ROLE_PATH = Qt.UserRole


class _List(QListWidget):
    """List that keeps navigation keys for itself instead of letting window shortcuts steal them."""

    files_dropped = Signal(list)
    delete_pressed = Signal()
    _OWN_KEYS = {Qt.Key_Up, Qt.Key_Down, Qt.Key_Home, Qt.Key_End, Qt.Key_PageUp, Qt.Key_PageDown,
                 Qt.Key_Return, Qt.Key_Enter, Qt.Key_Delete}

    def __init__(self):
        super().__init__()
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setAcceptDrops(True)
        self.setUniformItemSizes(True)

    def event(self, e):
        if e.type() == QEvent.ShortcutOverride and e.key() in self._OWN_KEYS \
                and not (e.modifiers() & (Qt.ControlModifier | Qt.AltModifier)):
            e.accept()
            return True
        return super().event(e)

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Return, Qt.Key_Enter) and self.currentItem():
            self.itemActivated.emit(self.currentItem())
            return
        if e.key() == Qt.Key_Delete:
            self.delete_pressed.emit()
            return
        super().keyPressEvent(e)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls() and e.source() is not self:
            e.acceptProposedAction()
        else:
            super().dragEnterEvent(e)

    def dragMoveEvent(self, e):
        if e.mimeData().hasUrls() and e.source() is not self:
            e.acceptProposedAction()
        else:
            super().dragMoveEvent(e)

    def dropEvent(self, e):
        if e.mimeData().hasUrls() and e.source() is not self:
            paths = [u.toLocalFile() or u.toString() for u in e.mimeData().urls()]
            self.files_dropped.emit(paths)
            e.acceptProposedAction()
        else:
            super().dropEvent(e)


class PlaylistPanel(QWidget):
    play_requested = Signal(int)
    changed = Signal()

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self._current_item: QListWidgetItem | None = None
        self.list = _List()
        self.list.itemActivated.connect(lambda it: self.play_requested.emit(self.list.row(it)))
        self.list.files_dropped.connect(self.add_paths)
        self.list.model().rowsMoved.connect(lambda *_: self.changed.emit())
        self.list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._menu)
        self.list.delete_pressed.connect(self.remove_selected)

        def tb(name, tip, slot, checkable=False):
            b = QToolButton()
            b.setIcon(icon(name))
            b.setIconSize(QSize(16, 16))
            b.setToolTip(tip)
            b.setFocusPolicy(Qt.NoFocus)
            b.setCheckable(checkable)
            b.clicked.connect(slot)
            return b

        self.btn_add = tb("open", "Add files", lambda: self.add_requested())
        self.btn_shuffle = tb("shuffle", "Shuffle", self._toggle_shuffle, True)
        self.btn_repeat = tb("repeat", "Repeat: off", self.cycle_repeat, True)
        self.btn_clear = QToolButton()
        self.btn_clear.setText("Clear")
        self.btn_clear.setFocusPolicy(Qt.NoFocus)
        self.btn_clear.clicked.connect(self.clear)
        self.btn_sort = QToolButton()
        self.btn_sort.setText("Sort")
        self.btn_sort.setFocusPolicy(Qt.NoFocus)
        self.btn_sort.clicked.connect(self.sort_by_name)

        bar = QHBoxLayout()
        bar.setContentsMargins(4, 4, 4, 0)
        bar.addWidget(self.btn_add)
        bar.addWidget(self.btn_shuffle)
        bar.addWidget(self.btn_repeat)
        bar.addStretch(1)
        bar.addWidget(self.btn_sort)
        bar.addWidget(self.btn_clear)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addLayout(bar)
        lay.addWidget(self.list)
        self.sync_mode_buttons()

    # hook set by the main window for the "add" button
    def add_requested(self):
        pass

    # -- model --------------------------------------------------------------------------
    def count(self):
        return self.list.count()

    def path_at(self, i):
        it = self.list.item(i)
        return it.data(ROLE_PATH) if it else None

    def paths(self):
        return [self.path_at(i) for i in range(self.count())]

    def current_index(self):
        if self._current_item is None:
            return -1
        r = self.list.row(self._current_item)
        return r

    def _make_item(self, path):
        it = QListWidgetItem(display_name(path))
        it.setData(ROLE_PATH, path)
        it.setToolTip(path)
        return it

    def set_paths(self, paths):
        self.list.clear()
        self._current_item = None
        for p in paths:
            self.list.addItem(self._make_item(p))
        self.changed.emit()

    def add_paths(self, paths):
        """Add files/folders/URLs (expanding folders). Returns index of the first added item."""
        first = self.count()
        for p in expand_targets(paths):
            self.list.addItem(self._make_item(p))
        self.changed.emit()
        return first if self.count() > first else -1

    def set_current(self, i):
        f = QFont(self.list.font())
        if self._current_item is not None and self.list.row(self._current_item) >= 0:
            self._current_item.setFont(f)
            self._current_item.setText(display_name(self._current_item.data(ROLE_PATH)))
        self._current_item = self.list.item(i) if 0 <= i < self.count() else None
        if self._current_item is not None:
            f.setBold(True)
            self._current_item.setFont(f)
            self._current_item.setText("▶  " + display_name(self._current_item.data(ROLE_PATH)))
            self.list.scrollToItem(self._current_item)

    def clear(self):
        self.list.clear()
        self._current_item = None
        self.changed.emit()

    def remove_selected(self):
        for it in self.list.selectedItems():
            if it is self._current_item:
                self._current_item = None
            self.list.takeItem(self.list.row(it))
        self.changed.emit()

    def sort_by_name(self):
        cur = self._current_item.data(ROLE_PATH) if self._current_item else None
        paths = sorted(self.paths(), key=lambda p: natural_key(display_name(p)))
        self.set_paths(paths)
        if cur in paths:
            self.set_current(paths.index(cur))

    # -- navigation ---------------------------------------------------------------------
    def next_index(self, auto=False):
        n = self.count()
        if n == 0:
            return None
        cur = self.current_index()
        rep = self.settings["repeat"]
        if auto and rep == "one" and cur >= 0:
            return cur
        if self.settings["shuffle"] and n > 1:
            choices = [i for i in range(n) if i != cur]
            return random.choice(choices)
        nxt = cur + 1
        if nxt >= n:
            return 0 if (rep == "all" or not auto) else None
        return nxt

    def prev_index(self):
        n = self.count()
        if n == 0:
            return None
        cur = self.current_index()
        return (cur - 1) % n if cur >= 0 else 0

    # -- modes --------------------------------------------------------------------------
    def cycle_repeat(self):
        order = ["off", "all", "one"]
        self.settings["repeat"] = order[(order.index(self.settings["repeat"]) + 1) % 3] \
            if self.settings["repeat"] in order else "off"
        self.sync_mode_buttons()
        return self.settings["repeat"]

    def _toggle_shuffle(self):
        self.settings["shuffle"] = not self.settings["shuffle"]
        self.sync_mode_buttons()

    def sync_mode_buttons(self):
        rep = self.settings["repeat"]
        self.btn_repeat.setChecked(rep != "off")
        self.btn_repeat.setToolTip({"off": "Repeat: off", "all": "Repeat: playlist",
                                    "one": "Repeat: current file"}.get(rep, "Repeat"))
        self.btn_repeat.setText("1" if rep == "one" else "")
        self.btn_repeat.setToolButtonStyle(Qt.ToolButtonTextBesideIcon if rep == "one"
                                           else Qt.ToolButtonIconOnly)
        self.btn_shuffle.setChecked(bool(self.settings["shuffle"]))

    # -- interaction --------------------------------------------------------------------
    def _menu(self, pos):
        it = self.list.itemAt(pos)
        m = QMenu(self)
        if it:
            m.addAction("Play", lambda: self.play_requested.emit(self.list.row(it)))
            m.addAction("Remove", self.remove_selected)
            path = it.data(ROLE_PATH)
            if not is_url(path):
                m.addAction("Open Containing Folder",
                            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(path))))
            m.addSeparator()
        m.addAction("Add Files...", self.add_requested)
        m.addAction("Sort by Name", self.sort_by_name)
        m.addAction("Clear", self.clear)
        m.exec(self.list.viewport().mapToGlobal(pos))


def expand_targets(paths):
    out = []
    for p in paths:
        if not p:
            continue
        p = normalize_target(p)
        if is_url(p):
            out.append(p)
        elif os.path.isdir(p):
            out.extend(media_in_folder(p, recursive=True))
        elif os.path.isfile(p):
            out.append(p)
    return out


__all__ = ["PlaylistPanel", "expand_targets", "is_media"]
