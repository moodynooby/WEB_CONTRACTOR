"""Web Contractor - Textual TUI Application"""
import asyncio
import os
from dotenv import load_dotenv
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Header, Footer, Button, Static, RichLog, DataTable
from textual.binding import Binding
from textual import work
from discovery import Discovery
from outreach import Outreach
from email_sender import EmailSender
from lead_repository import LeadRepository

# Load environment variables from .env file
load_dotenv()


class WebContractorTUI(App):
    """Web Contractor Terminal User Interface"""

    CSS = """
    Screen {
        background: $surface;
    }

    #stats-container {
        height: 7;
        border: solid $primary;
        margin: 1;
    }

    .stat-box {
        width: 1fr;
        height: 5;
        border: solid $accent;
        margin: 0 1;
        padding: 1;
        content-align: center middle;
    }

    .stat-value {
        text-style: bold;
        color: $success;
    }

    #controls {
        height: 5;
        border: solid $primary;
        margin: 1;
        padding: 1;
    }

    #log-container {
        height: 1fr;
        border: solid $primary;
        margin: 1;
    }

    RichLog {
        height: 100%;
    }

    .success {
        color: $success;
    }

    .error {
        color: $error;
    }

    .info {
        color: $accent;
    }
    """

    BINDINGS = [
        Binding("d", "run_discovery", "Discovery"),
        Binding("a", "run_audit", "Audit"),
        Binding("g", "generate_emails", "Generate Emails"),
        Binding("s", "send_emails", "Send Emails"),
        Binding("r", "refresh_stats", "Refresh"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self):
        super().__init__()
        
        # Thread-safe logging wrapper
        def thread_safe_log(message: str, style: str = ""):
            try:
                self.call_from_thread(self.write_log, message, style)
            except:
                # Fallback if app is not running or other issues
                print(message)

        self.discovery = Discovery(logger=thread_safe_log)
        self.outreach = Outreach(logger=thread_safe_log)
        self.email_sender = EmailSender(logger=thread_safe_log)
        self.repo = LeadRepository()
        self.repo.setup_database()

    def compose(self) -> ComposeResult:
        """Create child widgets"""
        yield Header()
        
        with Container(id="stats-container"):
            with Horizontal():
                yield Static("", id="stat-leads", classes="stat-box", markup=True)
                yield Static("", id="stat-qualified", classes="stat-box", markup=True)
                yield Static("", id="stat-emails", classes="stat-box", markup=True)
                yield Static("", id="stat-pending", classes="stat-box", markup=True)
        
        with Container(id="log-container"):
            yield RichLog(id="activity-log", markup=True)
        
        yield Footer()

    def on_mount(self) -> None:
        """Initialize UI on mount"""
        self.title = "Web Contractor"
        self.sub_title = "Lead Discovery & Outreach Automation"
        self.refresh_stats()
        self.write_log("✓ Web Contractor initialized", "success")
        self.write_log("Press [d] Discovery, [a] Audit, [g] Generate, [s] Send, [q] Quit", "info")

    def write_log(self, message: str, style: str = ""):
        """Write to activity log"""
        log_widget = self.query_one("#activity-log", RichLog)
        if style == "success":
            log_widget.write(f"[green]✓[/green] {message}")
        elif style == "error":
            log_widget.write(f"[red]✗[/red] {message}")
        elif style == "info":
            log_widget.write(f"[cyan]ℹ[/cyan] {message}")
        else:
            log_widget.write(message)

    def refresh_stats(self) -> None:
        """Update statistics display"""
        stats = self.repo.get_stats()
        
        self.query_one("#stat-leads").update(
            f"[b]Total Leads[/b]\n[green]{stats['total_leads']}[/green]"
        )
        self.query_one("#stat-qualified").update(
            f"[b]Qualified[/b]\n[yellow]{stats['qualified_leads']}[/yellow]"
        )
        self.query_one("#stat-emails").update(
            f"[b]Emails Sent[/b]\n[cyan]{stats['emails_sent']}[/cyan]"
        )
        self.query_one("#stat-pending").update(
            f"[b]Pending[/b]\n[magenta]{stats['emails_pending']}[/magenta]"
        )

    @work(exclusive=True, thread=True)
    def action_run_discovery(self) -> None:
        """Run discovery pipeline (Stage 0 + Stage A)"""
        
        try:
            self.discovery.run(max_queries=5)
        except Exception as e:
            self.call_from_thread(self.write_log, f"Discovery failed: {e}", "error")
        finally:
            self.call_from_thread(self.refresh_stats)

    @work(exclusive=True, thread=True)
    def action_run_audit(self) -> None:
        """Run audit pipeline (Stage B)"""
        
        try:
            self.outreach.audit_leads(limit=10)
        except Exception as e:
            self.call_from_thread(self.write_log, f"Audit failed: {e}", "error")
        finally:
            self.call_from_thread(self.refresh_stats)

    @work(exclusive=True, thread=True)
    def action_generate_emails(self) -> None:
        """Generate emails (Stage C)"""
        
        try:
            self.outreach.generate_emails(limit=10)
        except Exception as e:
            self.call_from_thread(self.write_log, f"Email generation failed: {e}", "error")
        finally:
            self.call_from_thread(self.refresh_stats)

    @work(exclusive=True, thread=True)
    def action_send_emails(self) -> None:
        """Send pending emails"""
        
        try:
            self.email_sender.send_pending_emails(limit=5)
        except Exception as e:
            self.call_from_thread(self.write_log, f"Email sending failed: {e}", "error")
        finally:
            self.call_from_thread(self.refresh_stats)

    def action_refresh_stats(self) -> None:
        """Refresh statistics"""
        self.refresh_stats()
        self.write_log("Statistics refreshed", "info")


if __name__ == "__main__":
    app = WebContractorTUI()
    app.run()
