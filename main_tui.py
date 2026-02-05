"""Web Contractor - Textual TUI Application"""
import asyncio
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Header, Footer, Button, Static, Log, DataTable
from textual.binding import Binding
from textual import work
from discovery import Discovery
from outreach import Outreach
from email_sender import EmailSender
from lead_repository import LeadRepository


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

    Button {
        margin: 0 1;
    }

    #log-container {
        height: 1fr;
        border: solid $primary;
        margin: 1;
    }

    Log {
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
        self.discovery = Discovery()
        self.outreach = Outreach()
        self.email_sender = EmailSender()
        self.repo = LeadRepository()
        self.repo.setup_database()

    def compose(self) -> ComposeResult:
        """Create child widgets"""
        yield Header()
        
        with Container(id="stats-container"):
            with Horizontal():
                yield Static("", id="stat-leads", classes="stat-box")
                yield Static("", id="stat-qualified", classes="stat-box")
                yield Static("", id="stat-emails", classes="stat-box")
                yield Static("", id="stat-pending", classes="stat-box")
        
        with Horizontal(id="controls"):
            yield Button("Discovery [d]", id="btn-discovery", variant="primary")
            yield Button("Audit [a]", id="btn-audit", variant="success")
            yield Button("Generate [g]", id="btn-generate", variant="warning")
            yield Button("Send [s]", id="btn-send", variant="error")
            yield Button("Refresh [r]", id="btn-refresh", variant="default")
        
        with Container(id="log-container"):
            yield Log(id="activity-log")
        
        yield Footer()

    def on_mount(self) -> None:
        """Initialize UI on mount"""
        self.title = "Web Contractor - Ultra-Minimal TUI"
        self.sub_title = "Lead Discovery & Outreach Automation"
        self.refresh_stats()
        self.log("✓ Web Contractor TUI initialized", "success")
        self.log("Press [d] Discovery, [a] Audit, [g] Generate, [s] Send, [q] Quit", "info")

    def log(self, message: str, style: str = ""):
        """Write to activity log"""
        log_widget = self.query_one("#activity-log", Log)
        if style == "success":
            log_widget.write_line(f"[green]✓[/green] {message}")
        elif style == "error":
            log_widget.write_line(f"[red]✗[/red] {message}")
        elif style == "info":
            log_widget.write_line(f"[cyan]ℹ[/cyan] {message}")
        else:
            log_widget.write_line(message)

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
        self.log("Starting Discovery Pipeline...", "info")
        self.call_from_thread(self._disable_buttons)
        
        try:
            result = self.discovery.run(max_queries=5)
            self.call_from_thread(
                self.log,
                f"Discovery complete: {result['leads_found']} leads found, {result['leads_saved']} saved",
                "success"
            )
        except Exception as e:
            self.call_from_thread(self.log, f"Discovery failed: {e}", "error")
        finally:
            self.call_from_thread(self._enable_buttons)
            self.call_from_thread(self.refresh_stats)

    @work(exclusive=True, thread=True)
    def action_run_audit(self) -> None:
        """Run audit pipeline (Stage B)"""
        self.log("Starting Audit Pipeline...", "info")
        self.call_from_thread(self._disable_buttons)
        
        try:
            result = self.outreach.audit_leads(limit=10)
            self.call_from_thread(
                self.log,
                f"Audit complete: {result['audited']} audited, {result['qualified']} qualified",
                "success"
            )
        except Exception as e:
            self.call_from_thread(self.log, f"Audit failed: {e}", "error")
        finally:
            self.call_from_thread(self._enable_buttons)
            self.call_from_thread(self.refresh_stats)

    @work(exclusive=True, thread=True)
    def action_generate_emails(self) -> None:
        """Generate emails (Stage C)"""
        self.log("Starting Email Generation...", "info")
        self.call_from_thread(self._disable_buttons)
        
        try:
            result = self.outreach.generate_emails(limit=10)
            self.call_from_thread(
                self.log,
                f"Email generation complete: {result['generated']} emails created",
                "success"
            )
        except Exception as e:
            self.call_from_thread(self.log, f"Email generation failed: {e}", "error")
        finally:
            self.call_from_thread(self._enable_buttons)
            self.call_from_thread(self.refresh_stats)

    @work(exclusive=True, thread=True)
    def action_send_emails(self) -> None:
        """Send pending emails"""
        self.log("Starting Email Sender...", "info")
        self.call_from_thread(self._disable_buttons)
        
        try:
            result = self.email_sender.send_pending_emails(limit=5)
            self.call_from_thread(
                self.log,
                f"Email sending complete: {result['sent']} sent, {result['failed']} failed",
                "success"
            )
        except Exception as e:
            self.call_from_thread(self.log, f"Email sending failed: {e}", "error")
        finally:
            self.call_from_thread(self._enable_buttons)
            self.call_from_thread(self.refresh_stats)

    def action_refresh_stats(self) -> None:
        """Refresh statistics"""
        self.refresh_stats()
        self.log("Statistics refreshed", "info")

    def _disable_buttons(self) -> None:
        """Disable all action buttons"""
        for btn_id in ["btn-discovery", "btn-audit", "btn-generate", "btn-send"]:
            self.query_one(f"#{btn_id}", Button).disabled = True

    def _enable_buttons(self) -> None:
        """Enable all action buttons"""
        for btn_id in ["btn-discovery", "btn-audit", "btn-generate", "btn-send"]:
            self.query_one(f"#{btn_id}", Button).disabled = False

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button clicks"""
        button_id = event.button.id
        if button_id == "btn-discovery":
            self.action_run_discovery()
        elif button_id == "btn-audit":
            self.action_run_audit()
        elif button_id == "btn-generate":
            self.action_generate_emails()
        elif button_id == "btn-send":
            self.action_send_emails()
        elif button_id == "btn-refresh":
            self.action_refresh_stats()


if __name__ == "__main__":
    app = WebContractorTUI()
    app.run()
