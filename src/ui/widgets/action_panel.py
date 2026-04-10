"""Action Panel Widget.

Material-styled action buttons for pipeline operations.
"""

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QPushButton
from PyQt6.QtCore import pyqtSignal


class ActionPanel(QWidget):
    """Action buttons for pipeline operations.

    Signals:
        discovery_requested: Emitted when Discovery button is clicked.
        audit_requested: Emitted when Audit button is clicked.
        email_requested: Emitted when Generate Emails button is clicked.
        pipeline_requested: Emitted when Full Pipeline button is clicked.
        atlas_requested: Emitted when View Analytics button is clicked.
    """

    discovery_requested = pyqtSignal()
    audit_requested = pyqtSignal()
    email_requested = pyqtSignal()
    pipeline_requested = pyqtSignal()
    atlas_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.discovery_btn: QPushButton
        self.audit_btn: QPushButton
        self.email_btn: QPushButton
        self.pipeline_btn: QPushButton
        self.atlas_btn: QPushButton
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        """Build action buttons layout."""
        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        buttons = [
            ("🔍 Run Discovery", "discovery_btn"),
            ("📋 Run Audit", "audit_btn"),
            ("📧 Generate Emails", "email_btn"),
            ("🚀 Run Full Pipeline", "pipeline_btn"),
            ("📊 View Analytics (Atlas)", "atlas_btn"),
        ]

        for text, attr in buttons:
            btn = QPushButton(text)
            btn.setMinimumHeight(38)
            setattr(self, attr, btn)
            layout.addWidget(btn)

    def _connect_signals(self) -> None:
        """Connect button clicks to signals."""
        self.discovery_btn.clicked.connect(self.discovery_requested.emit)
        self.audit_btn.clicked.connect(self.audit_requested.emit)
        self.email_btn.clicked.connect(self.email_requested.emit)
        self.pipeline_btn.clicked.connect(self.pipeline_requested.emit)
        self.atlas_btn.clicked.connect(self.atlas_requested.emit)

    def set_buttons_enabled(self, enabled: bool) -> None:
        """Enable or disable all action buttons.

        Args:
            enabled: Whether buttons should be enabled.
        """
        self.discovery_btn.setEnabled(enabled)
        self.audit_btn.setEnabled(enabled)
        self.email_btn.setEnabled(enabled)
        self.pipeline_btn.setEnabled(enabled)
        self.atlas_btn.setEnabled(enabled)
