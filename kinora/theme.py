"""Dark Fusion theme (same greys as the author's other apps) with a teal accent."""

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

BG = "#202020"
SURFACE = "#2B2B2B"
BORDER = "#404040"
TEXT = "#F0F0F0"
SUBTLE = "#A0A0A0"
HIGHLIGHT = "#3E3E42"
ACCENT = "#2BB3A3"

STYLE = f"""
QToolTip {{ color: {TEXT}; background: {SURFACE}; border: 1px solid {BORDER}; padding: 3px; }}
QMenu {{ background: {SURFACE}; border: 1px solid {BORDER}; padding: 4px; }}
QMenu::item {{ padding: 5px 28px 5px 24px; border-radius: 3px; }}
QMenu::item:selected {{ background: {HIGHLIGHT}; }}
QMenu::item:disabled {{ color: #6A6A6A; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 4px 8px; }}
QToolButton {{ border: none; border-radius: 4px; padding: 3px; color: {TEXT}; }}
QToolButton:hover {{ background: {HIGHLIGHT}; }}
QToolButton:checked {{ background: #35514D; }}
QDockWidget {{ color: {TEXT}; }}
QDockWidget::title {{ background: {SURFACE}; padding: 5px; }}
QListWidget, QTableWidget, QPlainTextEdit {{ background: {SURFACE}; border: 1px solid {BORDER}; }}
QListWidget::item {{ padding: 3px; }}
QListWidget::item:selected, QTableWidget::item:selected {{ background: {HIGHLIGHT}; color: {TEXT}; }}
QHeaderView::section {{ background: {SURFACE}; color: {SUBTLE}; border: none;
    border-bottom: 1px solid {BORDER}; padding: 4px; }}
QPushButton {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 4px; padding: 5px 14px; }}
QPushButton:hover {{ background: {HIGHLIGHT}; }}
QPushButton:default {{ border-color: {ACCENT}; }}
QLineEdit, QComboBox, QFontComboBox, QKeySequenceEdit {{
    background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 3px; padding: 3px; }}
QAbstractSpinBox QLineEdit, QComboBox QLineEdit, QKeySequenceEdit QLineEdit {{
    border: none; background: transparent; padding: 0; }}
QTabWidget::pane {{ border: 1px solid {BORDER}; top: -1px; }}
QTabBar::tab {{ background: {BG}; border: 1px solid {BORDER}; padding: 6px 14px; margin-right: -1px; }}
QTabBar::tab:selected {{ background: {SURFACE}; border-bottom-color: {SURFACE}; }}
QSlider::groove:horizontal {{ height: 4px; background: {BORDER}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 2px; }}
QSlider::handle:horizontal {{ width: 12px; margin: -5px 0; border-radius: 6px; background: {TEXT}; }}
"""


def apply(app: QApplication):
    app.setStyle("Fusion")
    pal = QPalette()
    roles = {
        QPalette.Window: BG, QPalette.WindowText: TEXT, QPalette.Base: SURFACE,
        QPalette.AlternateBase: "#262626", QPalette.ToolTipBase: SURFACE, QPalette.ToolTipText: TEXT,
        QPalette.Text: TEXT, QPalette.Button: SURFACE, QPalette.ButtonText: TEXT,
        QPalette.BrightText: "#FF6060", QPalette.Highlight: ACCENT, QPalette.HighlightedText: "#101010",
        QPalette.Link: ACCENT, QPalette.PlaceholderText: SUBTLE, QPalette.Mid: BORDER,
        QPalette.Dark: "#151515", QPalette.Light: HIGHLIGHT,
    }
    for role, c in roles.items():
        pal.setColor(role, QColor(c))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        pal.setColor(QPalette.Disabled, role, QColor("#6A6A6A"))
    app.setPalette(pal)
    app.setStyleSheet(STYLE)
