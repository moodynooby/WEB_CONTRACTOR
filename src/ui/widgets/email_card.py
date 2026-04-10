"""Email Card Widget.

Individual email display card with action buttons for the review flow.
"""

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QTextEdit,
    QPushButton,
    QFrame,
    QMessageBox,
    QInputDialog,
)
from PyQt6.QtCore import pyqtSignal, Qt


class EmailCard(QFrame):
    """Card widget displaying a single email with review actions.

    Signals:
        approved: Emitted when Approve button is clicked (campaign_id, subject, body).
        deleted: Emitted when Delete button is clicked (campaign_id).
        refined: Emitted when Refine button is clicked (campaign_id, instructions).
        regenerated: Emitted when Regenerate button is clicked (campaign_id, lead_id).
        sent: Emitted when Send button is clicked (campaign_id, to_email, subject, body).
    """

    approved = pyqtSignal(str, str, str)
    deleted = pyqtSignal(str)
    refined = pyqtSignal(str, str)
    regenerated = pyqtSignal(str, str)
    sent = pyqtSignal(str, str, str, str)

    def __init__(
        self,
        email_data: dict,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.email_data = email_data
        self.campaign_id: str = email_data["id"]
        self.lead_id: str = email_data.get("lead_id", "")
        self.to_email: str = email_data.get("to_email", "")
        self._setup_ui()
        self._populate_data()

    def _setup_ui(self) -> None:
        """Build the card layout."""
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setObjectName("emailCard")
        self.setStyleSheet(
            """
            #emailCard {
                background-color: #2a2d32;
                border: 1px solid #3d444b;
                border-radius: 8px;
                padding: 12px;
            }
            #emailCard:hover {
                border-color: #3f98db;
            }
            QLabel#cardTitle {
                color: #fcfcfc;
                font-weight: bold;
                font-size: 14px;
            }
            QLabel#cardSubtitle {
                color: #aaa;
                font-size: 12px;
            }
            QLabel#cardLabel {
                color: #888;
                font-size: 11px;
            }
            QLineEdit#subjectEdit {
                background-color: #1e2125;
                color: #fcfcfc;
                border: 1px solid #3d444b;
                border-radius: 4px;
                padding: 6px;
                font-size: 13px;
                font-weight: bold;
            }
            QLineEdit#subjectEdit:focus {
                border-color: #3f98db;
            }
            QTextEdit#bodyEdit {
                background-color: #1e2125;
                color: #fcfcfc;
                border: 1px solid #3d444b;
                border-radius: 4px;
                padding: 6px;
                font-size: 12px;
                font-family: monospace;
            }
            QTextEdit#bodyEdit:focus {
                border-color: #3f98db;
            }
            """
        )

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        header = QHBoxLayout()
        self.title_label = QLabel()
        self.title_label.setObjectName("cardTitle")
        header.addWidget(self.title_label)

        header.addStretch()

        self.status_label = QLabel()
        self.status_label.setObjectName("cardSubtitle")
        header.addWidget(self.status_label)

        layout.addLayout(header)

        self.to_email_label = QLabel()
        self.to_email_label.setObjectName("cardSubtitle")
        layout.addWidget(self.to_email_label)

        subject_label = QLabel("Subject:")
        subject_label.setObjectName("cardLabel")
        layout.addWidget(subject_label)

        self.subject_edit = QLineEdit()
        self.subject_edit.setObjectName("subjectEdit")
        layout.addWidget(self.subject_edit)

        body_label = QLabel("Body:")
        body_label.setObjectName("cardLabel")
        layout.addWidget(body_label)

        self.body_edit = QTextEdit()
        self.body_edit.setObjectName("bodyEdit")
        self.body_edit.setMinimumHeight(180)
        layout.addWidget(self.body_edit)

        self.links_label = QLabel()
        self.links_label.setObjectName("cardSubtitle")
        self.links_label.setWordWrap(True)
        self.links_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextBrowserInteraction
        )
        layout.addWidget(self.links_label)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(6)

        self.approve_btn = QPushButton("✅ Approve")
        self.approve_btn.setMinimumHeight(32)
        self.approve_btn.setToolTip("Approve and mark as ready to send")

        self.delete_btn = QPushButton("🗑️ Delete")
        self.delete_btn.setMinimumHeight(32)
        self.delete_btn.setToolTip("Delete this email permanently")

        self.refine_btn = QPushButton("🔧 Refine")
        self.refine_btn.setMinimumHeight(32)
        self.refine_btn.setToolTip("Refine email using AI instructions")

        self.regenerate_btn = QPushButton("🔁 Regenerate")
        self.regenerate_btn.setMinimumHeight(32)
        self.regenerate_btn.setToolTip("Regenerate email from scratch using LLM")

        self.send_btn = QPushButton("📧 Send")
        self.send_btn.setMinimumHeight(32)
        self.send_btn.setToolTip("Send email via SMTP immediately")

        btn_layout.addWidget(self.approve_btn)
        btn_layout.addWidget(self.delete_btn)
        btn_layout.addWidget(self.refine_btn)
        btn_layout.addWidget(self.regenerate_btn)
        btn_layout.addWidget(self.send_btn)
        btn_layout.addStretch()

        layout.addLayout(btn_layout)

        self._connect_signals()

    def _connect_signals(self) -> None:
        """Connect button clicks to handlers."""
        self.approve_btn.clicked.connect(self._on_approve)
        self.delete_btn.clicked.connect(self._on_delete)
        self.refine_btn.clicked.connect(self._on_refine)
        self.regenerate_btn.clicked.connect(self._on_regenerate)
        self.send_btn.clicked.connect(self._on_send)

    def _populate_data(self) -> None:
        """Fill the card with email data."""
        business = self.email_data.get("business_name", "Unknown")
        self.title_label.setText(business)

        status = self.email_data.get("status", "needs_review")
        self.status_label.setText(f"Status: {status}")

        self.to_email_label.setText(f"To: {self.to_email}")

        self.subject_edit.setText(self.email_data.get("subject", ""))

        self.body_edit.setPlainText(self.email_data.get("body", ""))

        links_parts = []
        social_links = self.email_data.get("social_links", {})
        if isinstance(social_links, dict):
            for key, url in social_links.items():
                if url:
                    links_parts.append(f"{key}: {url}")
        contact_form = self.email_data.get("contact_form_url")
        if contact_form:
            links_parts.append(f"Contact Form: {contact_form}")
        if links_parts:
            self.links_label.setText(" | ".join(links_parts))
        else:
            self.links_label.setText("")

    def _on_approve(self) -> None:
        """Handle Approve button click."""
        subject = self.subject_edit.text().strip()
        body = self.body_edit.toPlainText().strip()
        if not subject or not body:
            QMessageBox.warning(self, "Validation Error", "Subject and body cannot be empty.")
            return
        self.approved.emit(self.campaign_id, subject, body)

    def _on_delete(self) -> None:
        """Handle Delete button click."""
        business = self.email_data.get("business_name", "this email")
        reply = QMessageBox.question(
            self,
            "Confirm Delete",
            f"Are you sure you want to delete the email for '{business}'?\n\nThis action cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.deleted.emit(self.campaign_id)

    def _on_refine(self) -> None:
        """Handle Refine button click — opens instructions dialog."""
        instructions, ok = QInputDialog.getMultiLineText(
            self,
            "Refine Email",
            "Enter instructions for refining the email:\n\n"
            "Examples:\n"
            "• Make it shorter and more direct\n"
            "• Add a stronger call-to-action\n"
            "• Make the tone more casual",
            "",
        )
        if ok and instructions.strip():
            self.refined.emit(self.campaign_id, instructions.strip())

    def _on_regenerate(self) -> None:
        """Handle Regenerate button click."""
        business = self.email_data.get("business_name", "this email")
        reply = QMessageBox.question(
            self,
            "Confirm Regenerate",
            f"Regenerate the email for '{business}' from scratch?\n\n"
            "This will replace the current subject and body with a new LLM-generated version.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.regenerated.emit(self.campaign_id, self.lead_id)

    def _on_send(self) -> None:
        """Handle Send button click."""
        subject = self.subject_edit.text().strip()
        body = self.body_edit.toPlainText().strip()
        if not subject or not body:
            QMessageBox.warning(self, "Validation Error", "Subject and body cannot be empty.")
            return
        if not self.to_email:
            QMessageBox.warning(self, "Validation Error", "No recipient email address.")
            return
        reply = QMessageBox.question(
            self,
            "Confirm Send",
            f"Send this email to {self.to_email} right now?\n\n"
            "This will deliver the email via SMTP immediately.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.sent.emit(self.campaign_id, self.to_email, subject, body)

    def update_content(self, subject: str, body: str) -> None:
        """Update the card's subject and body fields.

        Args:
            subject: New subject line.
            body: New email body text.
        """
        self.subject_edit.setText(subject)
        self.body_edit.setPlainText(body)

    def mark_as(self, status: str) -> None:
        """Update the displayed status label.

        Args:
            status: New status text to display.
        """
        self.status_label.setText(f"Status: {status}")
