"""Email Review Dialog.

Main dialog for reviewing and managing generated emails.
"""

from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QScrollArea,
    QWidget,
    QMessageBox,
    QSpinBox,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QCloseEvent

from database.repository import (
    get_emails_for_review,
    update_email_content,
    delete_email,
)
from database.connection import is_connected
from outreach.generator import EmailGenerator
from outreach.sender import EmailSender
from ui.widgets.email_card import EmailCard
from infra.logging import get_logger

logger = get_logger(__name__)


class EmailReviewDialog(QDialog):
    """Modal dialog for reviewing generated emails.

    Displays emails needing review as editable cards with actions:
    Approve, Delete, Refine, Regenerate, Send.

    Signals:
        review_complete: Emitted when dialog closes after actions.
    """

    review_complete = pyqtSignal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.email_generator = EmailGenerator()
        self.email_sender = EmailSender()
        self.cards: list[EmailCard] = []
        self._setup_ui()
        self._load_emails()

    def _setup_ui(self) -> None:
        """Build the dialog layout."""
        self.setWindowTitle("Email Review")
        self.resize(800, 700)
        self.setMinimumSize(700, 500)

        self.setStyleSheet(
            """
            QDialog {
                background-color: #31363b;
            }
            QLabel#dialogTitle {
                color: #fcfcfc;
                font-size: 18px;
                font-weight: bold;
            }
            QLabel#dialogSubtitle {
                color: #aaa;
                font-size: 12px;
            }
            QPushButton {
                background-color: #3d444b;
                color: #fcfcfc;
                border: 1px solid #4d545b;
                border-radius: 4px;
                padding: 6px 14px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #4d545b;
                border-color: #3f98db;
            }
            QPushButton:pressed {
                background-color: #2a2d32;
            }
            """
        )

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        header = QHBoxLayout()
        self.title_label = QLabel("Email Review")
        self.title_label.setObjectName("dialogTitle")
        header.addWidget(self.title_label)

        header.addStretch()

        self.count_label = QLabel()
        self.count_label.setObjectName("dialogSubtitle")
        header.addWidget(self.count_label)

        layout.addLayout(header)

        controls = QHBoxLayout()
        controls.setSpacing(8)

        limit_label = QLabel("Limit:")
        limit_label.setObjectName("dialogSubtitle")
        controls.addWidget(limit_label)

        self.limit_spin = QSpinBox()
        self.limit_spin.setRange(1, 200)
        self.limit_spin.setValue(50)
        self.limit_spin.setFixedWidth(60)
        self.limit_spin.setStyleSheet(
            """
            QSpinBox {
                background-color: #1e2125;
                color: #fcfcfc;
                border: 1px solid #3d444b;
                border-radius: 4px;
                padding: 4px;
            }
            """
        )
        controls.addWidget(self.limit_spin)

        self.refresh_btn = QPushButton("🔄 Refresh")
        self.refresh_btn.setMinimumHeight(32)
        controls.addWidget(self.refresh_btn)

        self.approve_all_btn = QPushButton("✅ Approve All")
        self.approve_all_btn.setMinimumHeight(32)
        controls.addWidget(self.approve_all_btn)

        controls.addStretch()

        self.close_btn = QPushButton("Close")
        self.close_btn.setMinimumHeight(32)
        controls.addWidget(self.close_btn)

        layout.addLayout(controls)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            """
            QScrollArea {
                border: none;
                background-color: transparent;
            }
            QScrollBar:vertical {
                background-color: #1e2125;
                width: 10px;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical {
                background-color: #4d545b;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #5d646b;
            }
            """
        )

        self.cards_container = QWidget()
        self.cards_layout = QVBoxLayout(self.cards_container)
        self.cards_layout.setSpacing(10)
        self.cards_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        scroll.setWidget(self.cards_container)
        layout.addWidget(scroll)

        self.refresh_btn.clicked.connect(self._load_emails)
        self.approve_all_btn.clicked.connect(self._approve_all)
        self.close_btn.clicked.connect(self._close_safely)

    def _close_safely(self) -> None:
        """Close the dialog safely, ensuring cleanup."""
        self._set_cards_enabled(False)
        
        self._clear_cards()
        
        self.accept()

    def closeEvent(self, a0: QCloseEvent | None) -> None:
        """Handle window close event - cleanup safely."""
        self._set_cards_enabled(False)
        
        self._clear_cards()
        
        if a0 is not None:
            a0.accept()

    def _load_emails(self) -> None:
        """Fetch emails from database and populate cards."""
        if not is_connected():
            QMessageBox.warning(self, "Database Error", "Database is not connected.")
            return

        self._clear_cards()

        limit = self.limit_spin.value()
        emails = get_emails_for_review(limit=limit)

        if not emails:
            self.count_label.setText("No emails pending review")
            no_data = QLabel("No emails found needing review.\n\n"
                           "Run email generation first to create emails.")
            no_data.setObjectName("dialogSubtitle")
            no_data.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.cards_layout.addWidget(no_data)
            return

        self.count_label.setText(f"{len(emails)} email(s) to review")

        for email_data in emails:
            card = EmailCard(email_data)
            card.approved.connect(self._handle_approve)
            card.deleted.connect(self._handle_delete)
            card.refined.connect(self._handle_refine)
            card.regenerated.connect(self._handle_regenerate)
            card.sent.connect(self._handle_send)
            self.cards_layout.addWidget(card)
            self.cards.append(card)

        self.cards_layout.addStretch()

    def _clear_cards(self) -> None:
        """Remove all card widgets from the layout."""
        self.cards.clear()
        while self.cards_layout.count() > 1:
            item = self.cards_layout.takeAt(0)
            if item is not None:
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()

    def _set_cards_enabled(self, enabled: bool) -> None:
        """Enable or disable all card action buttons."""
        for card in self.cards:
            card.approve_btn.setEnabled(enabled)
            card.delete_btn.setEnabled(enabled)
            card.refine_btn.setEnabled(enabled)
            card.regenerate_btn.setEnabled(enabled)
            card.send_btn.setEnabled(enabled)

    def _handle_approve(self, campaign_id: str, subject: str, body: str) -> None:
        """Approve an email and mark as approved."""
        try:
            update_email_content(campaign_id, subject, body)
            card = self._find_card(campaign_id)
            if card:
                card.mark_as("approved")
                card.approve_btn.setEnabled(False)
            logger.info(f"Approved email {campaign_id}")
        except Exception as e:
            logger.error(f"Failed to approve email: {e}")
            QMessageBox.critical(self, "Error", f"Failed to approve email:\n{e}")

    def _handle_delete(self, campaign_id: str) -> None:
        """Delete an email campaign."""
        try:
            delete_email(campaign_id)
            card = self._find_card(campaign_id)
            if card:
                card.deleteLater()
                self.cards.remove(card)
            self.count_label.setText(f"{len(self.cards)} email(s) to review")
            logger.info(f"Deleted email {campaign_id}")
        except Exception as e:
            logger.error(f"Failed to delete email: {e}")
            QMessageBox.critical(self, "Error", f"Failed to delete email:\n{e}")

    def _handle_refine(self, campaign_id: str, instructions: str) -> None:
        """Refine an email using LLM."""
        card = self._find_card(campaign_id)
        if not card:
            return

        self._set_cards_enabled(False)
        card.refine_btn.setText("⏳ Refining...")

        try:
            subject = card.subject_edit.text().strip()
            body = card.body_edit.toPlainText().strip()

            result = self.email_generator.refine(subject, body, instructions)

            card.update_content(result["subject"], result["body"])
            card.refine_btn.setText("🔧 Refine")
            logger.info(f"Refined email {campaign_id}")
        except Exception as e:
            logger.error(f"Failed to refine email: {e}")
            QMessageBox.critical(self, "Error", f"Failed to refine email:\n{e}")
        finally:
            card.refine_btn.setText("🔧 Refine")
            self._set_cards_enabled(True)

    def _handle_regenerate(self, campaign_id: str, lead_id: str) -> None:
        """Regenerate an email from scratch using LLM."""
        card = self._find_card(campaign_id)
        if not card:
            return

        self._set_cards_enabled(False)
        card.regenerate_btn.setText("⏳ Regenerating...")

        try:
            from database.repository import get_lead_by_id

            lead = get_lead_by_id(lead_id)
            if not lead:
                QMessageBox.warning(self, "Error", "Lead not found for regeneration.")
                return

            result = self.email_generator.generate_for_lead(lead)
            card.update_content(result["subject"], result["body"])
            card.regenerate_btn.setText("🔁 Regenerate")
            logger.info(f"Regenerated email {campaign_id}")
        except Exception as e:
            logger.error(f"Failed to regenerate email: {e}")
            QMessageBox.critical(self, "Error", f"Failed to regenerate email:\n{e}")
        finally:
            card.regenerate_btn.setText("🔁 Regenerate")
            self._set_cards_enabled(True)

    def _handle_send(
        self, campaign_id: str, to_email: str, subject: str, body: str
    ) -> None:
        """Send an email via SMTP."""
        card = self._find_card(campaign_id)
        if not card:
            return

        self._set_cards_enabled(False)
        card.send_btn.setText("⏳ Sending...")

        try:
            success = self.email_sender.send_email(
                to_email=to_email,
                subject=subject,
                body=body,
                campaign_id=int(campaign_id) if campaign_id.isdigit() else None,
                lead_id=card.lead_id,
            )

            if success:
                card.mark_as("sent")
                card.send_btn.setEnabled(False)
                QMessageBox.information(
                    self, "Email Sent", f"Email sent successfully to {to_email}"
                )
                logger.info(f"Email sent to {to_email}")
            else:
                QMessageBox.warning(
                    self, "Send Failed", f"Failed to send email to {to_email}.\n\nCheck logs for details."
                )
                logger.error(f"Failed to send email to {to_email}")
        except Exception as e:
            logger.error(f"Email send error: {e}")
            QMessageBox.critical(self, "Error", f"Failed to send email:\n{e}")
        finally:
            card.send_btn.setText("📧 Send")
            self._set_cards_enabled(True)

    def _approve_all(self) -> None:
        """Approve all emails with current content."""
        if not self.cards:
            return

        reply = QMessageBox.question(
            self,
            "Approve All",
            f"Approve all {len(self.cards)} emails with their current content?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        approved_count = 0
        for card in list(self.cards):
            try:
                subject = card.subject_edit.text().strip()
                body = card.body_edit.toPlainText().strip()
                if subject and body:
                    update_email_content(card.campaign_id, subject, body)
                    card.mark_as("approved")
                    card.approve_btn.setEnabled(False)
                    approved_count += 1
            except Exception as e:
                logger.error(f"Failed to approve {card.campaign_id}: {e}")

        QMessageBox.information(
            self,
            "Approve Complete",
            f"Approved {approved_count} email(s).",
        )
        logger.info(f"Approved {approved_count} emails")

    def _find_card(self, campaign_id: str) -> EmailCard | None:
        """Find a card by campaign ID."""
        for card in self.cards:
            if card.campaign_id == campaign_id:
                return card
        return None
