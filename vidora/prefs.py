"""Preferences dialog, including the keyboard remapping table."""

import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QKeySequence
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QColorDialog, QComboBox, QDialog,
                               QDialogButtonBox, QDoubleSpinBox, QFileDialog, QFontComboBox,
                               QFormLayout, QHBoxLayout, QHeaderView, QKeySequenceEdit, QLabel,
                               QLineEdit, QMessageBox, QPushButton, QSpinBox, QTableWidget,
                               QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget)

from .actions import ACTIONS, BY_ID, keys_for
from .config import pictures_dir

HWDEC = [("auto-safe", "Automatic (recommended)"), ("auto-copy-safe", "Automatic, copy-back (safest)"),
         ("vaapi", "VA-API (Intel / AMD)"), ("nvdec", "NVDEC (NVIDIA)"), ("vdpau", "VDPAU"),
         ("vulkan", "Vulkan"), ("no", "Off (software decoding)")]


def _combo(items, current):
    cb = QComboBox()
    for value, label in items:
        cb.addItem(label, value)
    i = cb.findData(current)
    cb.setCurrentIndex(max(0, i))
    return cb


class ColorButton(QPushButton):
    def __init__(self, color):
        super().__init__()
        self.color = QColor(color)
        self.setFixedWidth(80)
        self.clicked.connect(self._pick)
        self._paint()

    def _paint(self):
        self.setText(self.color.name().upper())
        fg = "#000" if self.color.lightness() > 128 else "#FFF"
        self.setStyleSheet(f"background: {self.color.name()}; color: {fg};")

    def _pick(self):
        c = QColorDialog.getColor(self.color, self, "Choose color")
        if c.isValid():
            self.color = c
            self._paint()


class KeyEditDialog(QDialog):
    def __init__(self, label, keys, defaults, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Shortcut — {label}")
        self.defaults = defaults
        self.edits = []
        form = QFormLayout()
        for i in range(3):
            ed = QKeySequenceEdit(QKeySequence(keys[i]) if i < len(keys) else QKeySequence())
            if hasattr(ed, "setMaximumSequenceLength"):
                ed.setMaximumSequenceLength(1)
            if hasattr(ed, "setClearButtonEnabled"):
                ed.setClearButtonEnabled(True)
            self.edits.append(ed)
            form.addRow(["Primary", "Secondary", "Alternate"][i] + ":", ed)
        hint = QLabel("Click a field and press the key combination. Default: " +
                      (", ".join(defaults) if defaults else "none"))
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #A0A0A0;")
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel |
                              QDialogButtonBox.RestoreDefaults)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        bb.button(QDialogButtonBox.RestoreDefaults).clicked.connect(self._defaults)
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(hint)
        lay.addWidget(bb)

    def _defaults(self):
        for i, ed in enumerate(self.edits):
            ed.setKeySequence(QKeySequence(self.defaults[i]) if i < len(self.defaults) else QKeySequence())

    def keys(self):
        out = []
        for ed in self.edits:
            s = ed.keySequence().toString(QKeySequence.PortableText)
            if s and s not in out:
                out.append(s)
        return out


class PreferencesDialog(QDialog):
    def __init__(self, settings, parent=None, start_tab=None):
        super().__init__(parent)
        self.s = settings
        self.setWindowTitle("Preferences")
        self.resize(720, 560)
        self.tabs = QTabWidget()
        self.w = {}
        self._keys = {a.id: keys_for(a.id, settings["keys"] or {}) for a in ACTIONS}
        self.tabs.addTab(self._general(), "General")
        self.tabs.addTab(self._playback(), "Playback")
        self.tabs.addTab(self._video(), "Video")
        self.tabs.addTab(self._audio(), "Audio")
        self.tabs.addTab(self._subs(), "Subtitles")
        self.tabs.addTab(self._keyboard(), "Keyboard")
        if start_tab:
            for i in range(self.tabs.count()):
                if self.tabs.tabText(i) == start_tab:
                    self.tabs.setCurrentIndex(i)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._accept)
        bb.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(self.tabs)
        lay.addWidget(bb)

    # -- helpers --------------------------------------------------------------------------
    def _check(self, key, label):
        cb = QCheckBox(label)
        cb.setChecked(bool(self.s[key]))
        self.w[key] = cb
        return cb

    def _spin(self, key, lo, hi, suffix="", step=1):
        sp = QSpinBox()
        sp.setRange(lo, hi)
        sp.setSingleStep(step)
        sp.setValue(int(self.s[key]))
        if suffix:
            sp.setSuffix(suffix)
        self.w[key] = sp
        return sp

    def _dspin(self, key, lo, hi, step, decimals=2, suffix=""):
        sp = QDoubleSpinBox()
        sp.setRange(lo, hi)
        sp.setSingleStep(step)
        sp.setDecimals(decimals)
        sp.setValue(float(self.s[key]))
        if suffix:
            sp.setSuffix(suffix)
        self.w[key] = sp
        return sp

    def _choice(self, key, items):
        cb = _combo(items, self.s[key])
        self.w[key] = cb
        return cb

    def _text(self, key, placeholder=""):
        le = QLineEdit(str(self.s[key] or ""))
        le.setPlaceholderText(placeholder)
        self.w[key] = le
        return le

    @staticmethod
    def _page(form):
        page = QWidget()
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        form.setLabelAlignment(Qt.AlignRight)
        page.setLayout(form)
        return page

    # -- pages ----------------------------------------------------------------------------
    def _general(self):
        f = QFormLayout()
        f.addRow(self._check("resume_playback", "Resume files where I left off"))
        f.addRow(self._check("remember_volume", "Remember volume and mute between sessions"))
        f.addRow(self._check("auto_add_folder", "When opening one file, add the rest of its folder to the playlist"))
        f.addRow(self._check("single_instance", "Open files in the already running window"))
        f.addRow(self._check("fit_window_to_video", "Resize the window to fit each video"))
        f.addRow("Max auto window size:", self._spin("max_window_percent", 20, 100, " % of screen", 5))
        f.addRow("Always on top:", self._choice("on_top", [("never", "Never"), ("always", "Always"),
                                                           ("playing", "While playing")]))
        f.addRow(QLabel(""))
        f.addRow(QLabel("<b>Mouse</b>"))
        f.addRow(self._check("click_to_pause", "Click on video to play / pause"))
        f.addRow(self._check("double_click_fullscreen", "Double-click for fullscreen"))
        f.addRow("Mouse wheel:", self._choice("wheel_action", [("volume", "Volume (Ctrl+wheel seeks)"),
                                                               ("seek", "Seek (Ctrl+wheel = volume)")]))
        f.addRow("Middle click:", self._choice("middle_click", [("mute", "Mute"), ("pause", "Play / pause"),
                                                                ("fullscreen", "Fullscreen"),
                                                                ("none", "Nothing")]))
        f.addRow("Hide cursor after:", self._spin("hide_cursor_ms", 500, 10000, " ms", 250))
        f.addRow(QLabel(""))
        f.addRow(QLabel("<b>Advanced</b> (restart required)"))
        f.addRow("Video surface:", self._choice("video_surface", [
            ("auto", "Automatic (recommended)"),
            ("native", "Native mpv window (X11 / XWayland / Windows)"),
            ("opengl", "OpenGL inside Qt (Wayland / Windows)")]))
        hint = QLabel("If the video stays black while sound plays, try the other surface.")
        hint.setStyleSheet("color: #A0A0A0;")
        f.addRow(hint)
        mpv_dir = r"%APPDATA%\mpv" if sys.platform == "win32" else "~/.config/mpv"
        f.addRow(self._check("load_mpv_config", f"Load my mpv.conf, input.conf and scripts ({mpv_dir})"))
        from . import winassoc
        if winassoc.available():
            f.addRow(QLabel(""))
            f.addRow(QLabel("<b>Windows</b>"))
            row = QHBoxLayout()
            self._assoc_btn = QPushButton()
            self._assoc_btn.clicked.connect(self._toggle_assoc)
            row.addWidget(self._assoc_btn)
            row.addStretch(1)
            f.addRow(row)
            self._sync_assoc()
        return self._page(f)

    def _sync_assoc(self):
        from . import winassoc
        on = winassoc.is_registered()
        self._assoc_btn.setText("Remove Vidora from 'Open with' and Default apps" if on
                                else "Add Vidora to 'Open with' and Default apps...")

    def _toggle_assoc(self):
        from . import winassoc
        if winassoc.is_registered():
            winassoc.unregister()
        else:
            winassoc.register()
            QMessageBox.information(
                self, "Default apps",
                "Vidora is now listed under 'Open with' for video and audio files.\n\n"
                "Windows lets only you choose defaults: Settings will open next. Pick Vidora "
                "for the file types you want.")
            winassoc.open_default_apps()
        self._sync_assoc()

    def _playback(self):
        f = QFormLayout()
        f.addRow("Fine seek (Shift+arrows):", self._spin("seek_fine", 1, 600, " s"))
        f.addRow("Seek (arrows):", self._spin("seek_small", 1, 600, " s"))
        f.addRow("Medium seek (Ctrl+arrows):", self._spin("seek_medium", 1, 3600, " s"))
        f.addRow("Large seek (Alt+arrows):", self._spin("seek_large", 1, 3600, " s"))
        f.addRow(self._check("precise_seek", "Precise seeking (exact frame, slightly slower)"))
        f.addRow("Speed step:", self._dspin("speed_step", 0.05, 1.0, 0.05, suffix="x"))
        f.addRow("Volume step:", self._spin("volume_step", 1, 25, " %"))
        f.addRow("Repeat:", self._choice("repeat", [("off", "Off"), ("one", "Current file"),
                                                    ("all", "Whole playlist")]))
        f.addRow(self._check("shuffle", "Shuffle playlist"))
        f.addRow(self._check("thumbnails", "Show thumbnail previews on the seek bar"))
        return self._page(f)

    def _video(self):
        f = QFormLayout()
        f.addRow("Hardware decoding:", self._choice("hwdec", HWDEC))
        f.addRow(self._check("deinterlace", "Deinterlace by default"))
        f.addRow(QLabel(""))
        f.addRow(QLabel("<b>Screenshots</b>"))
        row = QHBoxLayout()
        le = self._text("screenshot_dir", pictures_dir())
        browse = QPushButton("Browse...")
        browse.clicked.connect(lambda: self._browse_dir(le))
        row.addWidget(le)
        row.addWidget(browse)
        f.addRow("Folder:", row)
        f.addRow("Format:", self._choice("screenshot_format", [("png", "PNG (lossless)"),
                                                               ("jpg", "JPEG"), ("webp", "WebP")]))
        return self._page(f)

    def _audio(self):
        f = QFormLayout()
        f.addRow("Preferred languages:", self._text("audio_langs", "e.g. jpn,ja,eng,en"))
        f.addRow("Maximum volume:", self._spin("volume_max", 100, 400, " %", 10))
        f.addRow(self._check("pitch_correction", "Keep pitch when changing speed"))
        f.addRow(self._check("normalize", "Normalize loudness (dynamic)"))
        return self._page(f)

    def _subs(self):
        f = QFormLayout()
        f.addRow("Auto-load external files:", self._choice("sub_auto", [
            ("fuzzy", "Files containing the video name"), ("exact", "Exact name match"),
            ("all", "All subtitle files in the folder"), ("no", "Don't auto-load")]))
        f.addRow("Preferred languages:", self._text("sub_langs", "e.g. eng,en"))
        f.addRow("Character encoding:", self._text("sub_codepage", "auto (or e.g. cp1256, cp1251)"))
        f.addRow(QLabel(""))
        f.addRow(QLabel("<b>Style</b> (text subtitles such as SRT)"))
        font = QFontComboBox()
        font.setCurrentFont(QFont(self.s["sub_font"]))
        font.setEditText(self.s["sub_font"])  # keep aliases like "Sans" that the list lacks
        self.w["sub_font"] = font
        f.addRow("Font:", font)
        f.addRow("Size:", self._spin("sub_font_size", 10, 150))
        f.addRow(self._check("sub_bold", "Bold"))
        self.w["sub_color"] = ColorButton(self.s["sub_color"])
        f.addRow("Text color:", self.w["sub_color"])
        self.w["sub_border_color"] = ColorButton(self.s["sub_border_color"])
        f.addRow("Outline color:", self.w["sub_border_color"])
        f.addRow("Outline size:", self._dspin("sub_border_size", 0, 10, 0.5, 1))
        f.addRow("Scale:", self._dspin("sub_scale", 0.3, 4.0, 0.1))
        f.addRow("Vertical position:", self._spin("sub_pos", 0, 150))
        f.addRow(self._check("sub_override_ass", "Apply this style to styled (ASS/SSA) subtitles too"))
        return self._page(f)

    def _keyboard(self):
        page = QWidget()
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Filter actions or keys...")
        self.filter.textChanged.connect(self._filter_keys)
        self.table = QTableWidget(len(ACTIONS), 3)
        self.table.setHorizontalHeaderLabels(["Action", "Category", "Shortcuts"])
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        hh.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.Stretch)
        for row, a in enumerate(ACTIONS):
            it = QTableWidgetItem(a.label)
            it.setData(Qt.UserRole, a.id)
            self.table.setItem(row, 0, it)
            self.table.setItem(row, 1, QTableWidgetItem(a.category))
            self.table.setItem(row, 2, QTableWidgetItem(""))
            self._refresh_row(row)
        self.table.cellDoubleClicked.connect(lambda r, _c: self._edit_row(r))
        edit = QPushButton("Change...")
        edit.clicked.connect(lambda: self._edit_row(self.table.currentRow()))
        reset = QPushButton("Reset All to Defaults")
        reset.clicked.connect(self._reset_keys)
        btns = QHBoxLayout()
        btns.addWidget(QLabel("Double-click an action to change its keys."))
        btns.addStretch(1)
        btns.addWidget(edit)
        btns.addWidget(reset)
        lay = QVBoxLayout(page)
        lay.addWidget(self.filter)
        lay.addWidget(self.table)
        lay.addLayout(btns)
        return page

    # -- keyboard tab logic ---------------------------------------------------------------
    def _refresh_row(self, row):
        aid = self.table.item(row, 0).data(Qt.UserRole)
        keys = self._keys[aid]
        txt = ",   ".join(QKeySequence(k).toString(QKeySequence.NativeText) for k in keys)
        item = self.table.item(row, 2)
        item.setText(txt)
        f = item.font()
        f.setBold(list(keys) != list(BY_ID[aid].keys))
        item.setFont(f)

    def _filter_keys(self, text):
        t = text.casefold().strip()
        for row in range(self.table.rowCount()):
            hay = " ".join(self.table.item(row, c).text() for c in range(3)).casefold()
            self.table.setRowHidden(row, bool(t) and t not in hay)

    def _edit_row(self, row):
        if row < 0:
            return
        aid = self.table.item(row, 0).data(Qt.UserRole)
        a = BY_ID[aid]
        dlg = KeyEditDialog(a.label, self._keys[aid], list(a.keys), self)
        if dlg.exec() != QDialog.Accepted:
            return
        new = dlg.keys()
        norm = lambda k: QKeySequence(k).toString(QKeySequence.PortableText)
        for k in new:
            for other, okeys in self._keys.items():
                if other != aid and norm(k) in [norm(x) for x in okeys]:
                    ans = QMessageBox.question(
                        self, "Shortcut in use",
                        f"“{QKeySequence(k).toString(QKeySequence.NativeText)}” is already used by "
                        f"“{BY_ID[other].label}”.\nMove it to “{a.label}”?")
                    if ans != QMessageBox.Yes:
                        return
                    self._keys[other] = [x for x in okeys if norm(x) != norm(k)]
        self._keys[aid] = new
        for r in range(self.table.rowCount()):
            self._refresh_row(r)

    def _reset_keys(self):
        self._keys = {a.id: list(a.keys) for a in ACTIONS}
        for r in range(self.table.rowCount()):
            self._refresh_row(r)

    def _browse_dir(self, le):
        d = QFileDialog.getExistingDirectory(self, "Screenshot folder", le.text() or pictures_dir())
        if d:
            le.setText(d)

    # -- save -----------------------------------------------------------------------------
    def _accept(self):
        for key, w in self.w.items():
            if isinstance(w, QCheckBox):
                self.s[key] = w.isChecked()
            elif isinstance(w, QSpinBox):
                self.s[key] = w.value()
            elif isinstance(w, QDoubleSpinBox):
                self.s[key] = round(w.value(), 3)
            elif isinstance(w, QFontComboBox):
                self.s[key] = w.currentText().strip() or w.currentFont().family()
            elif isinstance(w, QComboBox):
                self.s[key] = w.currentData()
            elif isinstance(w, ColorButton):
                self.s[key] = w.color.name().upper()
            elif isinstance(w, QLineEdit):
                self.s[key] = w.text().strip()
        self.s["keys"] = {aid: keys for aid, keys in self._keys.items()
                          if list(keys) != list(BY_ID[aid].keys)}
        self.accept()
