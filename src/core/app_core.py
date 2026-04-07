"""Unified Application Layer for Web Contractor

Centralized service management and lifecycle control.
"""

from typing import Callable, Dict, Optional

from core.db import init_db, close_db
from core.discovery import PlaywrightScraper
from core.email import EmailSender, EmailGenerator
from core.audit import AuditOrchestrator
from core.logging import get_logger


class WebContractorApp:
    """Unified application layer - manages all services."""

    def __init__(self):
        self.logger = get_logger(__name__)
        self._scraper: Optional[PlaywrightScraper] = None
        self._email_sender: Optional[EmailSender] = None
        self._email_generator: Optional[EmailGenerator] = None
        self._orchestrator: Optional[AuditOrchestrator] = None
        self._initialized = False

    def initialize(self) -> None:
        """Initialize database and services."""
        if self._initialized:
            return

        self.logger.info("Initializing database...")
        init_db()

        self.logger.info("Initializing services...")
        self._scraper = PlaywrightScraper()
        self._orchestrator = AuditOrchestrator()
        self._email_sender = EmailSender()
        self._email_generator = EmailGenerator()

        self._initialized = True
        self.logger.info("Initialization complete")

    def shutdown(self) -> None:
        """Cleanup resources."""
        if not self._initialized:
            return

        self.logger.info("Shutting down...")
        close_db()
        self._initialized = False
        self.logger.info("Shutdown complete")

    @property
    def scraper(self) -> PlaywrightScraper:
        """Get scraper service, initializing if needed."""
        if not self._initialized:
            self.initialize()
        return self._scraper  # type: ignore[return-value]

    @property
    def orchestrator(self) -> AuditOrchestrator:
        """Get audit orchestrator service, initializing if needed."""
        if not self._initialized:
            self.initialize()
        return self._orchestrator  # type: ignore[return-value]

    @property
    def email_sender(self) -> EmailSender:
        """Get email sender service, initializing if needed."""
        if not self._initialized:
            self.initialize()
        return self._email_sender  # type: ignore[return-value]

    @property
    def email_generator(self) -> EmailGenerator:
        """Get email generator service, initializing if needed."""
        if not self._initialized:
            self.initialize()
        return self._email_generator  # type: ignore[return-value]

    def run_discovery(
        self,
        max_queries: Optional[int] = None,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> Dict:
        """Run lead discovery pipeline."""
        self.logger.info("Starting discovery...")
        try:
            result = self.scraper.run(
                max_queries=max_queries,
                progress_callback=progress_callback,
            )
            self.logger.info("Discovery complete")
            return result
        except Exception as e:
            self.logger.error(f"Discovery failed: {e}")
            raise

    def run_audit(
        self,
        limit: int = 20,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> Dict:
        """Run lead audit pipeline using multi-agent orchestrator."""
        self.logger.info("Starting multi-agent audit...")
        try:
            result = self.orchestrator.run(
                limit=limit,
                progress_callback=progress_callback,
            )
            self.logger.info(
                f"Audit complete: {result.get('audited', 0)} audited, "
                f"{result.get('qualified', 0)} qualified"
            )
            return result
        except Exception as e:
            self.logger.error(f"Audit failed: {e}")
            raise

    def generate_emails(
        self,
        limit: int = 20,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> Dict:
        """Generate outreach emails for qualified leads."""
        self.logger.info("Starting email generation...")
        try:
            result = self.email_generator.generate(
                limit=limit,
                progress_callback=progress_callback,
            )
            self.logger.info(
                f"Email generation complete: {result.get('generated', 0)} emails"
            )
            return result
        except Exception as e:
            self.logger.error(f"Email generation failed: {e}")
            raise

    def run_unified_pipeline(
        self,
        limit: int = 20,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> Dict:
        """Run unified audit + email generation pipeline."""
        self.logger.info("Starting unified pipeline...")
        try:
            audit_result = self.run_audit(
                limit=limit, progress_callback=progress_callback
            )
            email_result = self.generate_emails(limit=limit)

            result = {
                "processed": audit_result.get("audited", 0),
                "qualified": audit_result.get("qualified", 0),
                "emails_generated": email_result.get("generated", 0),
            }
            self.logger.info(
                f"Pipeline complete: {result.get('processed', 0)} processed, "
                f"{result.get('qualified', 0)} qualified, "
                f"{result.get('emails_generated', 0)} emails generated"
            )
            return result
        except Exception as e:
            self.logger.error(f"Pipeline failed: {e}")
            raise

    def send_email(
        self,
        to_email: str,
        subject: str,
        body: str,
        campaign_id: Optional[int] = None,
        lead_id: Optional[str] = None,
    ) -> bool:
        """Send single email."""
        try:
            success = self.email_sender.send_email(
                to_email=to_email,
                subject=subject,
                body=body,
                campaign_id=campaign_id,
                lead_id=lead_id,
            )
            if success:
                self.logger.info(f"Email sent to {to_email}")
            else:
                self.logger.error(f"Email send failed for {to_email}")
            return success
        except Exception as e:
            self.logger.error(f"Email send error: {e}")
            raise
