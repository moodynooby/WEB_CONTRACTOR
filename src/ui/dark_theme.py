"""Dark Theme Configuration for PyQt5.

Applies Breeze Dark color palette using Qt's native QPalette.
No heavy QSS stylesheets - just clean, native dark styling.
"""

from PyQt5.QtGui import QPalette, QColor


def apply_dark_theme(app) -> None:
    """Apply Breeze Dark theme to a QApplication instance.

    Uses Qt's native palette system for lightweight, performant dark styling.

    Args:
        app: QApplication instance to theme.
    """
    palette = QPalette()

    window_bg = QColor(49, 54, 59)
    window_text = QColor(252, 252, 252)
    base_bg = QColor(35, 38, 41)
    base_text = QColor(252, 252, 252)
    button_bg = QColor(61, 68, 75)
    button_text = QColor(252, 252, 252)
    highlight = QColor(63, 152, 219)
    highlighted_text = QColor(252, 252, 252)
    link = QColor(29, 153, 243)
    alternate_base = QColor(55, 61, 67)
    tool_tip_base = QColor(63, 152, 219)
    tool_tip_text = QColor(252, 252, 252)
    mid = QColor(85, 94, 103)
    shadow = QColor(20, 22, 24)
    light = QColor(75, 84, 93)
    dark = QColor(35, 38, 41)

    palette.setColor(QPalette.Window, window_bg)
    palette.setColor(QPalette.WindowText, window_text)

    palette.setColor(QPalette.Base, base_bg)
    palette.setColor(QPalette.Text, base_text)

    palette.setColor(QPalette.Button, button_bg)
    palette.setColor(QPalette.ButtonText, button_text)

    palette.setColor(QPalette.Highlight, highlight)
    palette.setColor(QPalette.HighlightedText, highlighted_text)
    palette.setColor(QPalette.Link, link)
    palette.setColor(QPalette.LinkVisited, link.darker(120))

    palette.setColor(QPalette.AlternateBase, alternate_base)
    palette.setColor(QPalette.ToolTipBase, tool_tip_base)
    palette.setColor(QPalette.ToolTipText, tool_tip_text)

    palette.setColor(QPalette.Mid, mid)
    palette.setColor(QPalette.Shadow, shadow)
    palette.setColor(QPalette.Light, light)
    palette.setColor(QPalette.Dark, dark)
    palette.setColor(QPalette.Midlight, light.lighter(115))

    disabled_text = QColor(150, 150, 150)
    palette.setColor(QPalette.Disabled, QPalette.WindowText, disabled_text)
    palette.setColor(QPalette.Disabled, QPalette.Text, disabled_text)
    palette.setColor(QPalette.Disabled, QPalette.ButtonText, disabled_text)
    palette.setColor(QPalette.Disabled, QPalette.Highlight, QColor(80, 80, 80))
    palette.setColor(QPalette.Disabled, QPalette.HighlightedText, disabled_text)

    inactive_highlight = QColor(50, 120, 170)
    palette.setColor(QPalette.Inactive, QPalette.Highlight, inactive_highlight)
    palette.setColor(QPalette.Inactive, QPalette.HighlightedText, highlighted_text)

    app.setPalette(palette)
