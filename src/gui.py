"""Web Contractor - PyQt6 Desktop GUI

Modern desktop application for:
- Triggering long-running pipeline tasks
- Monitoring real-time logs
- Viewing quick stats
- Opening MongoDB Atlas Charts dashboard
"""

import sys
import os
import webbrowser
from pathlib import Path

from PyQt6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QMessageBox,
    QApplication,
)
from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QCloseEvent

sys.path.insert(0, str(Path(__file__).parent))

from database.connection import is_connected, get_connection_status, init_db
from database.repository import (
    count_buckets,
    count_pending_audits,
    count_qualified_leads,
    count_emails_for_review,
)
from infra.logging import get_logger, get_log_streamer
from app import App
from ui.dark_theme import apply_dark_theme
from ui.widgets import StatusBar, ActionPanel, LogConsole
from ui.task_runner import TaskRunner, TaskManager

logger = get_logger(__name__)


class WebContractorGUI(QMainWindow):
    """Main PyQt6 application window."""

    def __init__(self):
        super().__init__()
        self.app: App | None = None
        self.task_manager = TaskManager()
        self.log_poller_timer = QTimer()
        self._log_queue = None

        self._setup_window()
        self._build_ui()
        self._connect_signals()
        self._check_db_connection()
        self._init_app()

    def _setup_window(self) -> None:
        """Configure main window properties."""
        self.setWindowTitle("Web Contractor")
        self.resize(900, 700)
        self.setMinimumSize(800, 600)

    def _build_ui(self) -> None:
        """Build the complete UI layout."""
        central = QWidget()
        self.setCentralWidget(central)

        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        self.status_bar = StatusBar()
        main_layout.addWidget(self.status_bar)

        self.action_panel = ActionPanel()
        main_layout.addWidget(self.action_panel)

        self.log_console = LogConsole()
        main_layout.addWidget(self.log_console)

    def _connect_signals(self) -> None:
        """Connect widget signals to handlers."""
        self.action_panel.discovery_requested.connect(self._run_discovery)
        self.action_panel.audit_requested.connect(self._run_audit)
        self.action_panel.email_requested.connect(self._run_email_generation)
        self.action_panel.pipeline_requested.connect(self._run_full_pipeline)
        self.action_panel.atlas_requested.connect(self._open_atlas_dashboard)

        self.log_poller_timer.timeout.connect(self._poll_logs)

    def _check_db_connection(self) -> None:
        """Check and display database connection status."""
        status = get_connection_status()
        connected = status.get("connected", False)
        healthy = status.get("healthy", False)

        if connected and healthy:
            db_name = status.get("database", "")
            self.status_bar.set_db_status(True, db_name)
        else:
            self.status_bar.set_db_status(False)

    def _init_app(self) -> None:
        """Initialize the App class and services."""
        if not is_connected():
            QMessageBox.critical(
                self,
                "Database Error",
                "MongoDB is not connected. Application cannot start.\n\n"
                "Please configure MONGODB_URI in your .env file.",
            )
            self.close()
            return

        try:
            logger.info("Initializing Web Contractor services...")
            self.app = App()
            self.app.initialize()
            logger.info("Services initialized successfully")
            self._refresh_stats()
        except Exception as e:
            logger.error(f"Failed to initialize services: {e}")
            QMessageBox.critical(
                self,
                "Initialization Error",
                f"Failed to initialize services:\n{e}",
            )

    def _setup_log_streamer(self) -> None:
        """Setup log streamer subscription for GUI."""
        streamer = get_log_streamer()
        self._log_queue = streamer.subscribe()
        self.log_poller_timer.start(100)

    def _poll_logs(self) -> None:
        """Check log queue and display any new messages."""
        if self._log_queue is None:
            return
        try:
            while True:
                message, _level = self._log_queue.get_nowait()
                self.log_console.append_message(message)
        except Exception:
            pass  

    def _refresh_stats(self) -> None:
        """Update quick stats from database."""
        if not is_connected():
            return

        try:
            stats = {
                "Buckets": count_buckets(),
                "Pending Audits": count_pending_audits(),
                "Qualified Leads": count_qualified_leads(),
                "Emails for Review": count_emails_for_review(),
            }
            self.status_bar.update_stats(stats)
        except Exception as e:
            logger.error(f"Failed to refresh stats: {e}")

    def _run_discovery(self) -> None:
        """Run discovery pipeline in background thread."""
        if self.task_manager.is_running("discovery"):
            QMessageBox.warning(self, "Busy", "Discovery is already running.")
            return
        if self.app is None:
            QMessageBox.critical(self, "Error", "Application not initialized.")
            return

        app = self.app
        self._run_task(
            "discovery",
            lambda: app.run_discovery(),
            "Discovery",
        )

    def _run_audit(self) -> None:
        """Run audit pipeline in background thread."""
        if self.task_manager.is_running("audit"):
            QMessageBox.warning(self, "Busy", "Audit is already running.")
            return
        if self.app is None:
            QMessageBox.critical(self, "Error", "Application not initialized.")
            return

        app = self.app
        self._run_task(
            "audit",
            lambda: app.run_audit(limit=20),
            "Audit",
        )

    def _run_email_generation(self) -> None:
        """Run email generation in background thread."""
        if self.task_manager.is_running("email"):
            QMessageBox.warning(self, "Busy", "Email generation is already running.")
            return
        if self.app is None:
            QMessageBox.critical(self, "Error", "Application not initialized.")
            return

        app = self.app
        self._run_task(
            "email",
            lambda: app.generate_emails(limit=20),
            "Email Generation",
        )

    def _run_full_pipeline(self) -> None:
        """Run full unified pipeline in background thread."""
        if self.task_manager.is_running("pipeline"):
            QMessageBox.warning(self, "Busy", "Pipeline is already running.")
            return
        if self.app is None:
            QMessageBox.critical(self, "Error", "Application not initialized.")
            return

        app = self.app
        self._run_task(
            "pipeline",
            lambda: app.run_unified_pipeline(limit=20),
            "Full Pipeline",
        )

    def _run_task(self, task_name: str, task_func, display_name: str) -> None:
        """Run a long-running task in a background thread.

        Args:
            task_name: Internal task identifier.
            task_func: Callable to execute.
            display_name: Human-readable task name.
        """

        def on_started(name: str):
            self.log_console.append_message(f"Starting {name}...")
            self.action_panel.set_buttons_enabled(False)

        def on_finished(name: str, result: dict, elapsed: float):
            summary = f"✓ {name} completed in {elapsed:.1f}s"
            for key, value in result.items():
                summary += f" | {key}: {value}"

            self.log_console.append_message(summary)
            self._refresh_stats()
            self.action_panel.set_buttons_enabled(True)

            QMessageBox.information(self, f"{name} Complete", summary)

        def on_failed(name: str, error: str):
            error_msg = f"✗ {name} failed: {error}"
            self.log_console.append_message(error_msg)
            logger.error(error_msg)
            self.action_panel.set_buttons_enabled(True)

            QMessageBox.critical(self, f"{name} Failed", f"{name} failed:\n{error}")

        runner = TaskRunner(task_name, task_func, display_name)
        runner.started.connect(on_started)
        runner.finished.connect(on_finished)
        runner.failed.connect(on_failed)

        self.task_manager.start_task(task_name, runner)

    def _open_atlas_dashboard(self) -> None:
        """Open MongoDB Atlas Charts dashboard in default browser."""
        atlas_url = os.getenv("ATLAS_CHARTS_URL", "https://charts.mongodb.com")
        webbrowser.open(atlas_url)
        self.log_console.append_message(f"Opened Atlas Charts: {atlas_url}")

    def closeEvent(self, a0: QCloseEvent | None) -> None:
        """Handle window close event - cleanup running tasks."""
        self.task_manager.stop_all()
        self.log_poller_timer.stop()
        if a0:
            a0.accept()


def main() -> None:
    """Launch PyQt6 GUI application."""
    if not is_connected():
        from main import check_db_connection as check_db

        if not check_db():
            print("[✗] Database connectivity check failed.")
            sys.exit(1)

        init_db()

    qt_app = QApplication(sys.argv)
    qt_app.setApplicationName("Web Contractor")

    apply_dark_theme(qt_app)

    gui = WebContractorGUI()
    gui._setup_log_streamer()
    gui.show()

    sys.exit(qt_app.exec())


if __name__ == "__main__":
    main()
