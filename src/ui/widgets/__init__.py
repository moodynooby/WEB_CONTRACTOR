"""Custom UI Widgets for Web Contractor.

Lightweight, dark-themed PyQt6 widgets for the main application window.
"""

from ui.widgets.status_bar import StatusBar
from ui.widgets.action_panel import ActionPanel
from ui.widgets.log_console import LogConsole
from ui.widgets.email_card import EmailCard
from ui.widgets.email_review_dialog import EmailReviewDialog

__all__ = ["StatusBar", "ActionPanel", "LogConsole", "EmailCard", "EmailReviewDialog"]
