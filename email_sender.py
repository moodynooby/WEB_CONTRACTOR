"""SMTP Email Sender with Connection Pooling

Performance optimizations:
- SMTP connection pooling with context manager
- Batch send with single connection reuse
- Connection health checks
"""

import json
import smtplib
import threading
import time
from contextlib import contextmanager
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Callable, List, Optional

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
        self.email_signature = self._load_email_signature()

    def _load_email_signature(self) -> str:
        """Load email signature from config file"""
        try:
            with open("config/email_prompts.json", "r") as f:
                config = json.load(f)
                sig_config = config.get("email_signature", {})
                template = sig_config.get("template", "\n\nBest regards,\nManas Doshi")
                return template.format(
                    name=sig_config.get("name", "Manas Doshi"),
                    company=sig_config.get("company", "Future Forwards"),
                    website=sig_config.get(
                        "website", "https://man27.netlify.app/services"
                    ),
                )
        except Exception:
            return "\n\nBest regards,\nManas Doshi,\nFuture Forwards - https://man27.netlify.app/services"

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
