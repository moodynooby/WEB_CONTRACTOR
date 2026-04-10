"""Dark Theme Configuration for PyQt6.

Applies Breeze Dark color palette using Qt's native QPalette.
No heavy QSS stylesheets - just clean, native dark styling.
"""

from PyQt6.QtGui import QPalette, QColor


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

    palette.setColor(QPalette.ColorRole.Window, window_bg)
    palette.setColor(QPalette.ColorRole.WindowText, window_text)

    palette.setColor(QPalette.ColorRole.Base, base_bg)
    palette.setColor(QPalette.ColorRole.Text, base_text)

    palette.setColor(QPalette.ColorRole.Button, button_bg)
    palette.setColor(QPalette.ColorRole.ButtonText, button_text)

    palette.setColor(QPalette.ColorRole.Highlight, highlight)
    palette.setColor(QPalette.ColorRole.HighlightedText, highlighted_text)
    palette.setColor(QPalette.ColorRole.Link, link)
    palette.setColor(QPalette.ColorRole.LinkVisited, link.darker(120))

    palette.setColor(QPalette.ColorRole.AlternateBase, alternate_base)
    palette.setColor(QPalette.ColorRole.ToolTipBase, tool_tip_base)
    palette.setColor(QPalette.ColorRole.ToolTipText, tool_tip_text)

    palette.setColor(QPalette.ColorRole.Mid, mid)
    palette.setColor(QPalette.ColorRole.Shadow, shadow)
    palette.setColor(QPalette.ColorRole.Light, light)
    palette.setColor(QPalette.ColorRole.Dark, dark)
    palette.setColor(QPalette.ColorRole.Midlight, light.lighter(115))

    disabled_text = QColor(150, 150, 150)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, disabled_text)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, disabled_text)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, disabled_text)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Highlight, QColor(80, 80, 80))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.HighlightedText, disabled_text)

    inactive_highlight = QColor(50, 120, 170)
    palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.Highlight, inactive_highlight)
    palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.HighlightedText, highlighted_text)

    app.setPalette(palette)
