"""Unified Application Layer for Web Contractor

Centralized service management, configuration loading, and lifecycle control.
This decouples the UI from direct service instantiation.
"""

import json
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from core.db_repository import init_db, close_db
from core.discovery import PlaywrightScraper
from core.email import EmailSender
from core.orchestrator import AuditOrchestrator


class Config:
    """Centralized configuration management."""

    def __init__(self, config_path: str = "config"):
        self.config_path = Path(config_path)
        self._cache: Dict[str, Dict] = {}

    def load(self, filename: str) -> Dict:
        """Load config file, using cache if available."""
        if filename in self._cache:
            return self._cache[filename]

        filepath = self.config_path / filename
        try:
            with open(filepath, "r") as f:
                data = json.load(f)
                self._cache[filename] = data  # type: ignore[assignment]
                return data  # type: ignore[return-value]
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def get(self, filename: str, key: str, default: Any = None) -> Any:
        """Get specific key from config file."""
        data = self.load(filename)
        return data.get(key, default)


class WebContractorApp:
    """
    Unified application layer - manages all services.
    
    Usage:
        app = WebContractorApp()
        app.initialize()
        app.run_discovery()
        app.run_audit()
        app.generate_emails()
        app.send_email(...)
        app.shutdown()
    """
    
    def __init__(
        self, 
        config_path: str = "config",
        logger: Optional[Callable[[str, str], None]] = None,
    ):
        self.config = Config(config_path)
        self.logger = logger or (lambda msg, style="": print(f"[{style}] {msg}"))
        
        self._scraper: Optional[PlaywrightScraper] = None
        self._email_sender: Optional[EmailSender] = None
        self._orchestrator: Optional[AuditOrchestrator] = None
        self._initialized = False

    def initialize(self) -> None:
        """Initialize database and services."""
        if self._initialized:
            return

        self.logger("Initializing database...", "info")
        init_db()

        self.logger("Initializing services...", "info")
        self._scraper = PlaywrightScraper(logger=self._log_wrapper("discovery"))
        self._orchestrator = AuditOrchestrator(logger=self._log_wrapper("audit"))
        self._email_sender = EmailSender(logger=self._log_wrapper("email"))
        
        self._initialized = True
        self.logger("Initialization complete", "success")
    
    def shutdown(self) -> None:
        """Cleanup resources."""
        if not self._initialized:
            return
        
        self.logger("Shutting down...", "info")
        close_db()
        self._initialized = False
        self.logger("Shutdown complete", "success")
    
    def _log_wrapper(self, service: str) -> Callable[[str, str], None]:
        """Create logger wrapper with service prefix."""
        def log(message: str, style: str = "") -> None:
            self.logger(f"[{service}] {message}", style)
        return log
    
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
    
    
    def run_discovery(
        self, 
        max_queries: Optional[int] = None,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> Dict:
        """Run lead discovery pipeline."""
        self.logger("Starting discovery...", "info")
        try:
            result = self.scraper.run(max_queries=max_queries)
            self.logger("Discovery complete", "success")
            return result  # type: ignore[return-value]
        except Exception as e:
            self.logger(f"Discovery failed: {e}", "error")
            raise
    
    def run_audit(
        self,
        limit: int = 20,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> Dict:
        """Run lead audit pipeline using multi-agent orchestrator."""
        self.logger("Starting multi-agent audit...", "info")
        try:
            result = self.orchestrator.audit_leads(
                limit=limit,
                progress_callback=progress_callback,
            )
            self.logger(f"Audit complete: {result.get('audited', 0)} audited, {result.get('qualified', 0)} qualified", "success")
            return result
        except Exception as e:
            self.logger(f"Audit failed: {e}", "error")
            raise
    
    def generate_emails(
        self,
        limit: int = 20,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> Dict:
        """Generate outreach emails for qualified leads.
        
        Note: For unified audit + email generation, use run_unified_pipeline() instead.
        """
        self.logger("Starting email generation...", "info")
        try:
            result = self.orchestrator.generate_emails(
                limit=limit,
                progress_callback=progress_callback,
            )
            self.logger(f"Email generation complete: {result.get('generated', 0)} emails", "success")
            return result
        except Exception as e:
            self.logger(f"Email generation failed: {e}", "error")
            raise

    def run_unified_pipeline(
        self,
        limit: int = 20,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> Dict:
        """Run unified audit + email generation pipeline."""
        self.logger("Starting unified pipeline...", "info")
        try:
            result = self.orchestrator.run_unified_pipeline(
                limit=limit,
                progress_callback=progress_callback,
            )
            self.logger(
                f"Pipeline complete: {result.get('processed', 0)} processed, "
                f"{result.get('qualified', 0)} qualified, "
                f"{result.get('emails_generated', 0)} emails generated",
                "success",
            )
            return result
        except Exception as e:
            self.logger(f"Pipeline failed: {e}", "error")
            raise

    def send_email(
        self,
        to_email: str,
        subject: str,
        body: str,
        campaign_id: Optional[int] = None,
    ) -> bool:
        """Send single email."""
        try:
            success = self.email_sender.send_email(
                to_email=to_email,
                subject=subject,
                body=body,
                campaign_id=campaign_id,
            )
            if success:
                self.logger(f"Email sent to {to_email}", "success")
            else:
                self.logger(f"Email send failed for {to_email}", "error")
            return success
        except Exception as e:
            self.logger(f"Email send error: {e}", "error")
            raise
