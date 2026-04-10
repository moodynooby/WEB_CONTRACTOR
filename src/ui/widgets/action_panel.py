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
        review_requested: Emitted when Review Emails button is clicked.
    """

    discovery_requested = pyqtSignal()
    audit_requested = pyqtSignal()
    email_requested = pyqtSignal()
    pipeline_requested = pyqtSignal()
    atlas_requested = pyqtSignal()
    review_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.discovery_btn: QPushButton
        self.audit_btn: QPushButton
        self.email_btn: QPushButton
        self.pipeline_btn: QPushButton
        self.atlas_btn: QPushButton
        self.review_btn: QPushButton
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
            ("🔎 Review Emails", "review_btn"),
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
        self.review_btn.clicked.connect(self.review_requested.emit)
        self.pipeline_btn.clicked.connect(self.pipeline_requested.emit)
        self.atlas_btn.clicked.connect(self.atlas_requested.emit)

    def set_buttons_enabled(self, enabled: bool, task_type: str | None = None) -> None:
        """Enable or disable action buttons based on running task type.

        Args:
            enabled: Whether buttons should be enabled.
            task_type: Type of task running ("discovery", "audit", "email", "pipeline").
                      None means enable/disable all buttons.

        Behavior:
            - task_type=None: Enable/disable ALL buttons (legacy behavior)
            - task_type="discovery": Block discovery + pipeline buttons
            - task_type="audit": Block audit + pipeline buttons
            - task_type="email": Block email generation + pipeline buttons
            - task_type="pipeline": Block ALL pipeline buttons (discovery, audit, email, pipeline)
            - Review and Analytics buttons are ALWAYS enabled (Tier 1)
        """
        blocking_map = {
            "discovery": [self.discovery_btn],
            "audit": [self.audit_btn],
            "email": [self.email_btn],
            "pipeline": [self.discovery_btn, self.audit_btn, self.email_btn, self.pipeline_btn],
        }

        if task_type is None:
            for btn in [self.discovery_btn, self.audit_btn, self.email_btn,
                        self.review_btn, self.pipeline_btn, self.atlas_btn]:
                btn.setEnabled(enabled)
            return

        buttons_to_control = blocking_map.get(task_type, [])

        if enabled:
            for btn in buttons_to_control:
                btn.setEnabled(True)
        else:
            for btn in buttons_to_control:
                btn.setEnabled(False)
