"""Dashboard Manager for Web Contractor TUI

Handles dashboard composition, stats display, and pipeline visualization.
"""

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import (
    Button,
    Footer,
    Header,
    RichLog,
    Static,
)

from core.db_repository import get_all_buckets
from core.db_models import Lead, Audit, EmailCampaign


class DashboardManager:
    """
    Manages dashboard UI components and updates.
    
    Responsibilities:
    - Pipeline visualization
    - Quick stats calculation
    - Status bar management
    - Dashboard composition
    """
    
    def __init__(self, app):
        """
        Args:
            app: Parent TUI app instance
        """
        self.app = app
    
    def compose_dashboard(self) -> ComposeResult:
        """Compose the dashboard screen content."""
        yield Header()

        with Container(id="dashboard-container"):
            with Vertical(id="pipeline-section"):
                yield Static(self.get_pipeline_visual(), id="pipeline-visual")

                with Horizontal(id="pipeline-actions"):
                    yield Button("🔍 Discovery", variant="primary", id="discovery-btn")
                    yield Button("📊 Audit", variant="primary", id="audit-btn")
                    yield Button("📧 Generate", variant="primary", id="generate-btn")
                    yield Button("✅ Review", variant="success", id="review-btn")
                    yield Button("🚀 Send", variant="warning", id="send-btn")

            yield Static(self.get_quick_stats(), id="quick-stats")

            with Vertical(id="log-section"):
                yield Static("[bold]📋 Activity Log[/bold]", id="log-title")
                yield RichLog(id="activity-log", markup=True, highlight=True, max_lines=100)

        yield Static(self.get_status_bar(), id="status-bar")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle dashboard button clicks."""
        button_id = event.button.id
        
        if button_id == "discovery-btn":
            self.app.action_run_discovery()
        elif button_id == "audit-btn":
            self.app.action_run_audit()
        elif button_id == "generate-btn":
            self.app.action_generate_emails()
        elif button_id == "review-btn":
            self.app.action_review_emails()
        elif button_id == "send-btn":
            self.app.action_review_emails()  
    
    def get_pipeline_visual(self) -> str:
        """Generate visual pipeline showing current operation state."""
        stages = [
            ("🔍", "Discovery", self.app.current_operation == "discovery"),
            ("📊", "Audit", self.app.current_operation == "audit"),
            ("📧", "Generate", self.app.current_operation == "generate"),
            ("✅", "Review", self.app.current_operation == "review"),
            ("🚀", "Send", self.app.current_operation == "send"),
        ]
        
        parts = []
        for icon, name, active in stages:
            if active:
                parts.append(f"[bold accent]{icon} {name}[/bold accent]")
            else:
                parts.append(f"[dim]{icon} {name}[/dim]")
        
        progress_str = f" ({self.app.operation_progress}%)" if self.app.operation_progress else ""
        return " → ".join(parts) + progress_str
    
    def get_quick_stats(self) -> str:
        """Generate quick stats bar."""
        buckets = len(get_all_buckets())
        total_leads = Lead.select().count()
        total_emails = EmailCampaign.select().count()
        total_audits = Audit.select().count()
        
        return f"[dim]Buckets: {buckets} | Leads: {total_leads} | Audits: {total_audits} | Emails: {total_emails}[/dim]"
    
    def get_status_bar(self) -> str:
        """Generate status bar message."""
        if self.app.current_operation:
            progress = f" ({self.app.operation_progress}%)" if self.app.operation_progress else ""
            return (
                f"[bold accent]⚙ {self.app.current_operation.title()} Running{progress}[/bold accent] "
                f"[dim]| Ctrl+C to cancel[/dim]"
            )
        else:
            return (
                "[dim]System Idle | "
                "Press 'd', 'a', 'g', 'v' for pipeline actions | "
            )
    
    def refresh_dashboard(self) -> None:
        """Refresh all dashboard components."""
        try:
            self.app.query_one("#quick-stats", Static).update(self.get_quick_stats())
            self.app.query_one("#status-bar", Static).update(self.get_status_bar())
            self.app.query_one("#pipeline-visual", Static).update(self.get_pipeline_visual())
        except Exception:
            pass  
    
