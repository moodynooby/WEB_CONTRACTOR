"""Web Contractor TUI - Main Application Entry Point

Simplified composition-only app class. All logic extracted to:
- ui.dashboard - Dashboard composition and updates
- ui.controllers - Action handlers and navigation  
- ui.screens.* - Individual screen implementations
- ui.components - Reusable UI components
"""

from typing import Dict, Optional
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import RichLog

from core.app_core import WebContractorApp
from ui.dashboard import DashboardManager
from ui.controllers import NavigationController
from ui.screens import (
    DatabaseScreen,
    ReviewScreen,
    MarketReviewScreen,
    QueryPerformanceScreen,
)

from dotenv import load_dotenv

load_dotenv()


class WebContractorTUI(App):
    """
    Web Contractor TUI - Simplified main application.

    Responsibilities:
    - App initialization and lifecycle
    - Service composition (dashboard, controllers)
    - Screen registration
    - Global key bindings
    """

    CSS = """
    #dashboard-container {
        padding: 1 2;
    }
    
    #pipeline-section {
        margin: 1 0;
        padding: 1;
        border: solid $primary;
    }
    
    #pipeline-visual {
        text-align: center;
        padding: 1;
    }
    
    #pipeline-actions {
        height: auto;
        align: center middle;
        margin: 1 0;
    }
    
    #pipeline-actions Button {
        margin: 0 1;
        min-width: 14;
    }
    
    #quick-stats {
        text-align: center;
        padding: 1;
        margin: 1 0;
    }
    
    #log-section {
        height: 1fr;
        margin: 1 0;
        border: solid $primary;
        padding: 1;
    }
    
    #log-title {
        padding: 0 1;
    }
    
    #activity-log {
        height: 1fr;
        background: $surface;
    }
    
    #status-bar {
        dock: bottom;
        height: 1;
        background: $primary-background;
        padding: 0 2;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit", show=True, priority=True),
        Binding("r", "refresh", "Refresh", show=True),
        Binding("d", "run_discovery", "Discovery", show=True),
        Binding("a", "run_audit", "Audit", show=True),
        Binding("g", "generate_emails", "Generate", show=True),
        Binding("e", "expand_markets", "Expand", show=False),
        Binding("v", "review_emails", "Review", show=True),
        Binding("b", "database_browser", "Database", show=True),
        Binding("p", "query_performance", "Perf", show=True),
    ]

    SCREENS: Dict[str, type] = {
        "database": DatabaseScreen,
        "review": ReviewScreen,
        "performance": QueryPerformanceScreen,
    }
    
    def __init__(self, app_core: Optional[WebContractorApp] = None):
        """
        Initialize TUI application.

        Args:
            app_core: Optional injected WebContractorApp instance
        """
        super().__init__()

        self.app_core = app_core or WebContractorApp(logger=self.write_log)

        self.current_operation: Optional[str] = None
        self.operation_progress: Optional[int] = None

        # Initialize managers immediately for compose()
        self.dashboard = DashboardManager(self)
        self.navigation = NavigationController(self, self.SCREENS, self.app_core)
    
    def compose(self) -> ComposeResult:
        """Compose main dashboard UI."""
        yield from self.dashboard.compose_dashboard()
    
    def on_mount(self) -> None:
        """Initialize application on mount."""
        self.title = "Web Contractor"
        self.sub_title = "Lead Discovery & Outreach Automation"

        # Initialize core services
        self.app_core.initialize()

        # Refresh dashboard to show initial state
        self.dashboard.refresh_dashboard()

        self.write_log(
            "Initialized"
        )
    
    def on_unmount(self) -> None:
        """Cleanup on unmount."""
        try:
            self.app_core.shutdown()
        except Exception:
            pass
    
    def write_log(self, message: str, style: str = "") -> None:
        """
        Write log message to console and logs screen if active.
        
        Args:
            message: Log message
            style: Optional style (success, error, info)
        """
        import sys
        from datetime import datetime
        
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        if style == "success":
            print(f"\033[92m[{timestamp}] ✓ {message}\033[0m", file=sys.stderr)
        elif style == "error":
            print(f"\033[91m[{timestamp}] ✗ {message}\033[0m", file=sys.stderr)
        elif style == "info":
            print(f"\033[96m[{timestamp}] ℹ {message}\033[0m", file=sys.stderr)
        else:
            print(f"[{timestamp}] {message}", file=sys.stderr)
        
        try:
            log_widget = self.query_one("#activity-log", RichLog)
            if style == "success":
                log_widget.write(f"[green]✓[/green] {message}")
            elif style == "error":
                log_widget.write(f"[red]✗[/red] {message}")
            elif style == "info":
                log_widget.write(f"[cyan]ℹ[/cyan] {message}")
            else:
                log_widget.write(message)
        except Exception:
            pass  # Dashboard may not be ready yet  
    
    def action_refresh(self) -> None:
        """Refresh dashboard."""
        if self.dashboard:
            self.dashboard.refresh_dashboard()
            self.notify("Dashboard refreshed")
    
    def action_run_discovery(self) -> None:
        """Run discovery pipeline."""
        self.run_worker(self.app_core.run_discovery, exclusive=True, thread=True)

    def action_run_audit(self) -> None:
        """Run audit pipeline."""
        self.run_worker(self.app_core.run_audit, exclusive=True, thread=True)

    def action_generate_emails(self) -> None:
        """Generate emails."""
        self.run_worker(self.app_core.generate_emails, exclusive=True, thread=True)

    def action_expand_markets(self) -> None:
        """Expand markets."""
        self.run_worker(self.app_core.scraper.discover_new_buckets, exclusive=True, thread=True)
    
    def action_review_emails(self) -> None:
        """Navigate to review screen."""
        self.push_screen(ReviewScreen())
    
    def action_database_browser(self) -> None:
        """Navigate to database browser."""
        self.push_screen(DatabaseScreen())
    
    def action_query_performance(self) -> None:
        """Navigate to performance screen."""
        self.push_screen(QueryPerformanceScreen())
    
    def show_market_review(self, suggestions: list) -> None:
        """Show market expansion suggestions."""
        self.push_screen(MarketReviewScreen(suggestions))

    def get_system_commands(self, screen: Screen) -> list:
        """Get system commands for command palette."""
        # Get default system commands from parent
        commands = list(super().get_system_commands(screen))

        # Add our custom commands
        commands.extend([
            ("Run Discovery", "Execute discovery pipeline", self.action_run_discovery),
            ("Run Audit", "Audit leads for quality", self.action_run_audit),
            ("Generate Emails", "Generate outreach emails", self.action_generate_emails),
            ("Review Emails", "Review generated emails", lambda: self.push_screen(ReviewScreen())),
            ("Database Browser", "Browse all data", lambda: self.push_screen(DatabaseScreen())),
            ("Query Performance", "View performance stats", lambda: self.push_screen(QueryPerformanceScreen())),
            ("Refresh Dashboard", "Refresh dashboard stats", self.dashboard.refresh_dashboard),
        ])

        return commands


if __name__ == "__main__":
    app = WebContractorTUI()
    app.run()
