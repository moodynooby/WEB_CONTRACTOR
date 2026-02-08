"""SMTP Email Sender with Connection Pooling

Performance optimizations:
- SMTP connection pooling with context manager
- Batch send with single connection reuse
- Connection health checks
"""

import smtplib
import threading
import time
from contextlib import contextmanager
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Callable, Dict, List, Optional, Tuple

from lead_repository import LeadRepository


class SMTPConnectionPool:
    """Thread-safe SMTP connection pool"""

    def __init__(
        self,
        smtp_server: str,
        smtp_port: int,
        email: str,
        password: str,
        max_connections: int = 3,
    ):
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        self.email = email
        self.password = password
        self.max_connections = max_connections
        self._pool: List[smtplib.SMTP] = []
        self._in_use: set = set()
        self._lock = threading.Lock()

    def _create_connection(self) -> smtplib.SMTP:
        """Create and authenticate new SMTP connection"""
        server = smtplib.SMTP(self.smtp_server, self.smtp_port)
        server.starttls()
        server.login(self.email, self.password)
        return server

    def _is_healthy(self, conn: smtplib.SMTP) -> bool:
        """Check if connection is still alive"""
        try:
            # SMTP.noop() returns a tuple (code, message)
            status = conn.noop()
            return status[0] == 250
        except Exception:
            return False

    def acquire(self) -> smtplib.SMTP:
        """Acquire an SMTP connection from the pool"""
        with self._lock:
            # Reuse available healthy connection
            for conn in list(self._pool):
                if conn not in self._in_use:
                    if self._is_healthy(conn):
                        self._in_use.add(conn)
                        return conn
                    else:
                        # Remove dead connection
                        try:
                            conn.quit()
                        except Exception:
                            pass
                        self._pool.remove(conn)

            # Create new connection if under limit
            if len(self._pool) < self.max_connections:
                conn = self._create_connection()
                self._pool.append(conn)
                self._in_use.add(conn)
                return conn

        # Wait for available connection
        while True:
            with self._lock:
                for conn in list(self._pool):
                    if conn not in self._in_use:
                        if self._is_healthy(conn):
                            self._in_use.add(conn)
                            return conn
            time.sleep(0.1)

    def release(self, conn: smtplib.SMTP) -> None:
        """Release an SMTP connection back to the pool"""
        with self._lock:
            self._in_use.discard(conn)

    def close_all(self) -> None:
        """Close all connections in the pool"""
        with self._lock:
            for conn in self._pool:
                try:
                    conn.quit()
                except Exception:
                    pass
            self._pool.clear()
            self._in_use.clear()

    @contextmanager
    def connection(self):
        """Context manager for acquiring and releasing connections"""
        conn = self.acquire()
        try:
            yield conn
        finally:
            self.release(conn)


class EmailSender:
    """SMTP Email Sender with connection pooling and batch sending"""

    def __init__(
        self,
        repo: Optional[LeadRepository] = None,
        logger: Optional[Callable] = None,
        smtp_server: str = "smtp.gmail.com",
        smtp_port: int = 587,
        email: Optional[str] = None,
        password: Optional[str] = None,
        pool_size: int = 3,
    ):
        self.repo = repo or LeadRepository()
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        self.email = email or __import__("os").getenv("GMAIL_EMAIL")
        self.password = password or __import__("os").getenv("GMAIL_PASSWORD")
        self.logger = logger
        self.pool_size = pool_size
        self._pool: Optional[SMTPConnectionPool] = None

    def log(self, message: str, style: str = "") -> None:
        """Log message to provided logger or print"""
        if self.logger:
            self.logger(message, style)
        else:
            print(message)

    def _get_pool(self) -> SMTPConnectionPool:
        """Get or create SMTP connection pool"""
        if self._pool is None:
            if not self.email or not self.password:
                raise ValueError("Email credentials not configured")
            self._pool = SMTPConnectionPool(
                self.smtp_server,
                self.smtp_port,
                self.email,
                self.password,
                max_connections=self.pool_size,
            )
        return self._pool

    def _cleanup(self) -> None:
        """Cleanup all resources"""
        if self._pool:
            self._pool.close_all()
            self._pool = None

    def send_email(self, to_email: str, subject: str, body: str) -> bool:
        """Send single email via SMTP using pooled connection"""
        try:
            msg = MIMEMultipart()
            msg["From"] = self.email
            msg["To"] = to_email
            msg["Subject"] = subject
            msg.attach(MIMEText(body, "plain"))

            with self._get_pool().connection() as server:
                server.send_message(msg)

            return True
        except Exception as e:
            self.log(f"Email send error: {e}", "error")
            return False

    def send_pending_emails(
        self,
        limit: int = 10,
        batch_size: int = 5,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> Dict:
        """Send all pending emails using pooled connections with batch processing"""
        self.log(f"\n{'=' * 60}")
        self.log("EMAIL SENDER: Sending Pending Emails (Connection Pool)")
        self.log(f"{'=' * 60}")

        if not self.email or not self.password:
            self.log("Gmail credentials not configured", "error")
            return {"sent": 0, "failed": 0}

        emails = self.repo.get_pending_emails(limit)
        if not emails:
            self.log("No pending emails to send.", "info")
            return {"sent": 0, "failed": 0}

        self.log(f"Sending {len(emails)} emails...", "info")

        sent = 0
        failed = 0
        results: List[Tuple[int, bool, Optional[str]]] = []

        try:
            # Process emails in batches
            for batch_start in range(0, len(emails), batch_size):
                batch = emails[batch_start : batch_start + batch_size]

                with self._get_pool().connection() as server:
                    for i, email_data in enumerate(batch, 1):
                        overall_index = batch_start + i

                        try:
                            msg = MIMEMultipart()
                            msg["From"] = self.email
                            msg["To"] = email_data["email"]
                            msg["Subject"] = email_data["subject"]
                            msg.attach(MIMEText(email_data["body"], "plain"))

                            server.send_message(msg)
                            results.append((email_data["campaign_id"], True, None))
                            sent += 1
                            self.log(
                                f"[{overall_index}/{len(emails)}] Sent to {email_data['email']}",
                                "success",
                            )
                        except Exception as e:
                            results.append(
                                (email_data["campaign_id"], False, str(e))
                            )
                            failed += 1
                            self.log(
                                f"[{overall_index}/{len(emails)}] Failed to {email_data['email']}: {e}",
                                "error",
                            )

                        if progress_callback:
                            progress_callback(
                                overall_index, len(emails), email_data["business_name"]
                            )

                        # Small delay to be polite to SMTP server
                        time.sleep(0.5)

            # Update database with results
            for campaign_id, success, error in results:
                self.repo.mark_email_sent(campaign_id, success, error)

        except Exception as e:
            self.log(f"SMTP Session failed: {e}", "error")
            # Update remaining as failed
            for campaign_id, _, _ in results:
                self.repo.mark_email_sent(campaign_id, False, error="SMTP session failed")

        finally:
            self._cleanup()

        self.log(f"\n{'=' * 60}")
        self.log(f"Email Sending Complete: {sent} sent, {failed} failed", "success")
        self.log(f"{'=' * 60}\n")

        return {"sent": sent, "failed": failed}

    def send_single_batch(
        self, email_data_list: List[Dict]
    ) -> List[Tuple[int, bool, Optional[str]]]:
        """Send a batch of emails using a single connection"""
        results: List[Tuple[int, bool, Optional[str]]] = []

        with self._get_pool().connection() as server:
            for email_data in email_data_list:
                try:
                    msg = MIMEMultipart()
                    msg["From"] = self.email
                    msg["To"] = email_data["email"]
                    msg["Subject"] = email_data["subject"]
                    msg.attach(MIMEText(email_data["body"], "plain"))

                    server.send_message(msg)
                    results.append((email_data["campaign_id"], True, None))
                except Exception as e:
                    error_msg: Optional[str] = str(e)
                    results.append((email_data["campaign_id"], False, error_msg))

                time.sleep(0.5)

        return results
