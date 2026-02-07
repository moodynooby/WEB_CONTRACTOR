"""Web Contractor - Textual TUI Application"""

import json
from typing import List, Dict
from dotenv import load_dotenv
from textual.app import App, ComposeResult
from textual.screen import Screen, ModalScreen
from textual.containers import Container, Horizontal, Vertical, Grid
from textual.widgets import (
    Header,
    Footer,
    Button,
    Static,
    RichLog,
    DataTable,
    Label,
    TextArea,
    Input,
    ProgressBar,
    TabbedContent,
    TabPane,
)
from textual.binding import Binding
from textual import work, on
from discovery import Discovery
from outreach import Outreach
from email_sender import EmailSender
from lead_repository import LeadRepository

# Load environment variables from .env file
load_dotenv()


class ReviewScreen(Screen):
    """Screen for reviewing generated emails"""

    BINDINGS = [
        Binding("escape", "app.pop_screen", "Back"),
        Binding("a", "approve_selected", "Approve"),
        Binding("e", "edit_selected", "Edit"),
        Binding("d", "delete_selected", "Delete"),
    ]

    def __init__(self, repo: LeadRepository):
        super().__init__()
        self.repo = repo
        self.selected_email = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            with Vertical(id="email-list-container"):
                yield Label("Emails Needing Review")
                yield DataTable(id="email-table")
            with Vertical(id="email-detail-container"):
                yield Label("Email Content")
                yield Static("Select an email to view details", id="email-details")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#email-table", DataTable)
        table.add_columns("Business", "Subject")
        table.cursor_type = "row"
        self.refresh_emails()

    def refresh_emails(self):
        table = self.query_one("#email-table", DataTable)
        table.clear()
        self.emails = self.repo.get_emails_needing_review()
        for i, email in enumerate(self.emails):
            table.add_row(
                email["business_name"], email["subject"], key=str(email["id"])
            )

        if not self.emails:
            self.query_one("#email-details").update("No emails pending review.")
            self.selected_email = None
        else:
            # If we had a selection, try to maintain it or select first
            if self.selected_email:
                exists = any(e["id"] == self.selected_email["id"] for e in self.emails)
                if not exists:
                    self.selected_email = self.emails[0]
                    table.move_cursor(row=0)
            else:
                self.selected_email = self.emails[0]
                table.move_cursor(row=0)
            self.update_detail_view()

    def on_data_table_row_selected(self, event: DataTable.RowSelected):
        if event.row_key.value is None:
            return
        email_id = int(event.row_key.value)
        self.selected_email = next(
            (e for e in self.emails if e["id"] == email_id), None
        )
        if self.selected_email:
            self.update_detail_view()

    def update_detail_view(self):
        if self.selected_email:
            content = f"[b]To:[/b] {self.selected_email.get('email', 'N/A')}\n"
            content += f"[b]Subject:[/b] {self.selected_email['subject']}\n\n"

            # Alternative Communications
            alt_comm = []
            if self.selected_email.get("contact_form_url"):
                alt_comm.append(
                    f"[cyan]Form:[/cyan] {self.selected_email['contact_form_url']}"
                )

            social = self.selected_email.get("social_links", {})
            for plat, link in social.items():
                alt_comm.append(f"[cyan]{plat.capitalize()}:[/cyan] {link}")

            if alt_comm:
                content += "[b]Alt Communications:[/b]\n" + "\n".join(alt_comm) + "\n\n"

            content += "[b]Message:[/b]\n"
            content += f"{self.selected_email['body']}"
            self.query_one("#email-details").update(content)

    def action_approve_selected(self):
        if self.selected_email:
            self.repo.update_email_status(self.selected_email["id"], "pending")
            self.notify(f"Approved email for {self.selected_email['business_name']}")
            self.refresh_emails()

    def action_delete_selected(self):
        if self.selected_email:
            self.repo.delete_email(self.selected_email["id"])
            self.notify(
                f"Deleted email for {self.selected_email['business_name']}",
                severity="error",
            )
            self.refresh_emails()

    async def action_edit_selected(self):
        if self.selected_email:
            edit_modal = EditEmailModal(self.selected_email)
            updated_email = await self.app.push_screen_wait(edit_modal)
            if updated_email:
                self.repo.update_email_content(
                    self.selected_email["id"],
                    updated_email["subject"],
                    updated_email["body"],
                )
                self.notify(
                    f"Updated and approved email for {self.selected_email['business_name']}"
                )
                self.refresh_emails()


class EditEmailModal(ModalScreen):
    """Modal for editing an email"""

    def __init__(self, email: Dict):
        super().__init__()
        self.email = email

    def compose(self) -> ComposeResult:
        with Grid(id="edit-grid"):
            yield Label(
                f"Editing Email for {self.email['business_name']}", id="edit-title"
            )
            yield Label("Subject:")
            yield Input(self.email["subject"], id="edit-subject")
            yield Label("Body:")
            yield TextArea(self.email["body"], id="edit-body")
            with Horizontal(id="edit-buttons"):
                yield Button("Save & Approve", variant="success", id="save-btn")
                yield Button("Cancel", variant="error", id="cancel-btn")

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "save-btn":
            subject = self.query_one("#edit-subject", Input).value
            body = self.query_one("#edit-body", TextArea).text
            self.dismiss({"subject": subject, "body": body})
        else:
            self.dismiss(None)


class MarketReviewScreen(Screen):
    """Screen for reviewing market expansion suggestions"""

    def __init__(self, suggestions: List[Dict], repo: LeadRepository):
        super().__init__()
        self.suggestions = suggestions
        self.repo = repo

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="market-review-container"):
            yield Label("LLM Market Expansion Suggestions")
            yield Static(
                "Review and approve new buckets or expansions", id="market-status"
            )
            yield DataTable(id="market-table")
            with Horizontal(id="market-actions"):
                yield Button("Approve Selected", variant="success", id="approve-market")
                yield Button("Reject Selected", variant="error", id="reject-market")
                yield Button("Done", id="done-market")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#market-table", DataTable)
        table.add_columns("Type", "Name", "Details")
        table.cursor_type = "row"
        self.refresh_table()

    def refresh_table(self):
        table = self.query_one("#market-table", DataTable)
        table.clear()
        for i, s in enumerate(self.suggestions):
            # s can be a new bucket or an expansion
            stype = "New Bucket" if "new_categories" not in s else "Expansion"
            name = s.get("name") or s.get("bucket_name") or "Expansion"
            details = str(s.get("categories") or s.get("new_categories", []))
            table.add_row(stype, name, details, key=str(i))

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "done-market":
            self.dismiss()
        elif event.button.id == "approve-market":
            table = self.query_one("#market-table", DataTable)
            if table.cursor_row is not None and table.cursor_row < len(
                self.suggestions
            ):
                idx = table.cursor_row
                suggestion = self.suggestions[idx]
                self.apply_suggestion(suggestion)
                self.suggestions.pop(idx)
                self.refresh_table()
                self.notify("Suggestion applied!")
        elif event.button.id == "reject-market":
            table = self.query_one("#market-table", DataTable)
            if table.cursor_row is not None and table.cursor_row < len(
                self.suggestions
            ):
                idx = table.cursor_row
                self.suggestions.pop(idx)
                self.refresh_table()
                self.notify("Suggestion rejected.")

    def apply_suggestion(self, s: Dict):
        if "new_categories" in s:
            # Expansion
            bucket_name = s.get("bucket_name")
            buckets = self.repo.get_all_buckets()
            bucket = next((b for b in buckets if b["name"] == bucket_name), None)
            if bucket:
                new_cats = list(
                    set(bucket.get("categories", []) + s.get("new_categories", []))
                )
                new_pats = list(
                    set(bucket.get("search_patterns", []) + s.get("new_patterns", []))
                )
                bucket["categories"] = new_cats
                bucket["search_patterns"] = new_pats

                # Geography
                geo_focus = self.repo.get_config("geographic_focus") or {}
                if "expanded" not in geo_focus:
                    geo_focus["expanded"] = {"cities": []}
                geo_focus["expanded"]["cities"] = list(
                    set(
                        geo_focus["expanded"].get("cities", [])
                        + s.get("new_cities", [])
                    )
                )
                self.repo.save_config("geographic_focus", geo_focus)

                segments = bucket.get("geographic_segments", [])
                if isinstance(segments, str):
                    segments = json.loads(segments)
                if "expanded" not in segments:
                    segments.append("expanded")
                    bucket["geographic_segments"] = segments

                self.repo.save_bucket(bucket)
        else:
            # New Bucket
            s["geographic_segments"] = ["tier_1_metros"]
            s["conversion_probability"] = 0.5
            s["monthly_target"] = 100
            self.repo.save_bucket(s)


class WebContractorTUI(App):
    """Web Contractor Terminal User Interface"""

    CSS = """
    Screen {
        background: $surface;
    }

    #stats-container, #perf-container {
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

    .perf-box {
        border: dashed $accent;
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

    #status-label {
        margin: 1;
        text-style: italic;
        color: $accent;
    }

    /* Settings Tab CSS */
    #settings-container {
        padding: 1;
    }
    
    .settings-section {
        border: tall $primary;
        margin-bottom: 1;
        padding: 1;
        height: auto;
    }

    /* Review Screen CSS */
    #email-list-container {
        width: 40%;
        border: solid $primary;
        margin: 1;
        padding: 1;
    }

    #email-detail-container {
        width: 60%;
        border: solid $primary;
        margin: 1;
        padding: 1;
    }

    #email-details {
        height: 1fr;
        overflow-y: scroll;
        padding: 1;
    }

    /* Edit Modal CSS */
    #edit-grid {
        grid-size: 1 6;
        grid-rows: 1 1 1 1 8 1;
        padding: 1 2;
        background: $surface;
        border: thick $primary;
        width: 80%;
        height: 80%;
        align: center middle;
    }

    #edit-title {
        text-style: bold;
        text-align: center;
    }

    #edit-buttons {
        height: 3;
        align: center middle;
        margin-top: 1;
    }

    #edit-body {
        height: 100%;
    }

    /* Market Review CSS */
    #market-review-container {
        padding: 1 2;
        border: thick $primary;
        margin: 1;
    }

    #market-table {
        height: 1fr;
        margin: 1 0;
    }

    #market-actions {
        height: 3;
        align: center middle;
    }
    """

    BINDINGS = [
        Binding("d", "run_discovery", "Discovery"),
        Binding("x", "expand_markets", "Expand Markets"),
        Binding("a", "run_audit", "Audit"),
        Binding("g", "generate_emails", "Generate Emails"),
        Binding("v", "review_emails", "Review"),
        Binding("s", "send_emails", "Send Emails"),
        Binding("r", "refresh_all", "Refresh All"),
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

        self.repo = LeadRepository()
        self.repo.setup_database()
        self.discovery = Discovery(repo=self.repo, logger=thread_safe_log)
        self.outreach = Outreach(repo=self.repo, logger=thread_safe_log)
        self.email_sender = EmailSender(repo=self.repo, logger=thread_safe_log)

    def compose(self) -> ComposeResult:
        """Create child widgets"""
        yield Header()

        with TabbedContent(id="main-tabs"):
            with TabPane("Dashboard", id="tab-dashboard"):
                yield Label("System Status: Idle", id="status-label")
                
                with Container(id="log-container"):
                    yield RichLog(id="activity-log", markup=True)

            with TabPane("Stats", id="tab-stats"):
                with Container(id="stats-container"):
                    with Horizontal():
                        yield Static("", id="stat-leads", classes="stat-box", markup=True)
                        yield Static("", id="stat-qualified", classes="stat-box", markup=True)
                        yield Static("", id="stat-review", classes="stat-box", markup=True)
                        yield Static("", id="stat-pending", classes="stat-box", markup=True)
                        yield Static("", id="stat-emails", classes="stat-box", markup=True)
                
                with Container(id="perf-container"):
                    with Horizontal():
                        yield Static("", id="stat-audit-perf", classes="stat-box perf-box", markup=True)
                        yield Static("", id="stat-gen-perf", classes="stat-box perf-box", markup=True)
                        yield Static("", id="stat-qual-perf", classes="stat-box perf-box", markup=True)
                        yield Static("", id="stat-reply-perf", classes="stat-box perf-box", markup=True)

            
            with TabPane("Settings", id="tab-settings"):
                with Vertical(id="settings-container"):
                    with Vertical(classes="settings-section"):
                        yield Label("[b]Geographic Focus[/b]")
                        yield Label("Current cities (JSON format):")
                        yield TextArea("", id="setting-geo-focus")
                        yield Button("Save Geographic Focus", variant="primary", id="save-geo-btn")

        yield Footer()

    def on_mount(self) -> None:
        """Initialize UI on mount"""
        self.title = "Web Contractor"
        self.sub_title = "Lead Discovery & Outreach Automation"
        self.refresh_stats()
        self.refresh_settings()
        self.write_log("✓ Web Contractor initialized", "success")
        self.write_log(
            "Press [d] Discovery, [a] Audit, [g] Generate, [v] Review, [s] Send, [q] Quit",
            "info",
        )

    def refresh_settings(self) -> None:
        """Load settings into UI"""
        geo_focus = self.repo.get_config("geographic_focus") or {}
        geo_text = json.dumps(geo_focus, indent=2)
        self.query_one("#setting-geo-focus", TextArea).text = geo_text

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

    @on(TabbedContent.TabActivated)
    def on_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        """Refresh stats when switching to the Stats tab"""
        if event.pane.id == "tab-stats":
            self.refresh_stats()

    def refresh_stats(self) -> None:
        """Update statistics display with consolidated data and performance metrics"""
        # Only refresh if the Stats tab is active
        try:
            tabbed = self.query_one(TabbedContent)
            if tabbed.active != "tab-stats":
                return
        except:
            pass

        stats = self.repo.get_stats()

        # Core Metrics
        self.query_one("#stat-leads").update(
            f"[b]Total Leads[/b]\n[green]{stats['total_leads']}[/green]"
        )
        self.query_one("#stat-qualified").update(
            f"[b]Qualified[/b]\n[yellow]{stats['qualified_leads']}[/yellow]"
        )
        self.query_one("#stat-review").update(
            f"[b]Needs Review[/b]\n[orange3]{stats['emails_review']}[/orange3]"
        )
        self.query_one("#stat-pending").update(
            f"[b]Approved[/b]\n[magenta]{stats['emails_pending']}[/magenta]"
        )
        self.query_one("#stat-emails").update(
            f"[b]Sent[/b]\n[cyan]{stats['emails_sent']}[/cyan]"
        )

        # Performance Metrics
        self.query_one("#stat-audit-perf").update(
            f"[b]Avg Audit[/b]\n[cyan]{stats['avg_audit_duration']:.1f}s[/cyan]"
        )
        self.query_one("#stat-gen-perf").update(
            f"[b]Avg Gen[/b]\n[cyan]{stats['avg_gen_duration']:.1f}s[/cyan]"
        )
        self.query_one("#stat-qual-perf").update(
            f"[b]Qual Rate[/b]\n[yellow]{stats['qualification_rate']:.1f}%[/yellow]"
        )
        self.query_one("#stat-reply-perf").update(
            f"[b]Reply Rate[/b]\n[green]{stats['reply_rate']:.1f}%[/green]"
        )

    def update_status(self, status: str = "Idle"):
        """Update status label"""
        sl = self.query_one("#status-label", Label)
        sl.update(f"System Status: {status}")

    @on(Button.Pressed, "#save-geo-btn")
    def save_geographic_focus(self) -> None:
        """Save geographic focus from textarea"""
        text = self.query_one("#setting-geo-focus", TextArea).text
        try:
            geo_focus = json.loads(text)
            self.repo.save_config("geographic_focus", geo_focus)
            self.notify("Geographic focus saved!")
            self.write_log("Geographic focus updated", "success")
        except Exception as e:
            self.notify(f"Invalid JSON: {e}", severity="error")

    @on(Button.Pressed, "#refresh-all-btn")
    def action_refresh_all(self) -> None:
        """Refresh statistics and settings"""
        self.refresh_stats()
        self.refresh_settings()
        self.write_log("System data refreshed", "info")
        self.notify("All data refreshed")

    @work(exclusive=True, thread=True)
    def action_expand_markets(self) -> None:
        """Discover new market buckets and expansions"""
        self.call_from_thread(self.update_status, "Expanding Markets...")
        try:
            suggestions = []
            # 1. New buckets
            new_buckets = self.discovery.discover_new_buckets()
            if isinstance(new_buckets, list):
                suggestions.extend(new_buckets)

            # 2. Expansion for current buckets
            for bucket in self.discovery.buckets:
                exp = self.discovery.expand_bucket(bucket["name"])
                if isinstance(exp, dict):
                    exp["bucket_name"] = bucket["name"]
                    suggestions.append(exp)

            if suggestions:
                self.call_from_thread(self.show_market_review, suggestions)
            else:
                self.call_from_thread(
                    self.write_log, "No new market suggestions found.", "info"
                )

        except Exception as e:
            self.call_from_thread(
                self.write_log, f"Market expansion failed: {e}", "error"
            )
        finally:
            self.call_from_thread(self.update_status, "Idle")
            self.call_from_thread(self.refresh_stats)

    def show_market_review(self, suggestions: List[Dict]):
        self.push_screen(
            MarketReviewScreen(suggestions, self.repo), lambda _: self.refresh_stats()
        )

    @work(exclusive=True, thread=True)
    def action_run_discovery(self) -> None:
        """Run discovery pipeline (Stage 0 + Stage A)"""
        self.call_from_thread(self.update_status, "Running Discovery...")
        try:
            self.discovery.run(max_queries=5)
        except Exception as e:
            self.call_from_thread(self.write_log, f"Discovery failed: {e}", "error")
        finally:
            self.call_from_thread(self.update_status, "Idle")
            self.call_from_thread(self.refresh_stats)

    @work(exclusive=True, thread=True)
    def action_run_audit(self) -> None:
        """Run audit pipeline (Stage B)"""
        self.call_from_thread(self.update_status, "Auditing Leads...")
        try:
            self.outreach.audit_leads(limit=10)
        except Exception as e:
            self.call_from_thread(self.write_log, f"Audit failed: {e}", "error")
        finally:
            self.call_from_thread(self.update_status, "Idle")
            self.call_from_thread(self.refresh_stats)

    @work(exclusive=True, thread=True)
    def action_generate_emails(self) -> None:
        """Generate emails (Stage C)"""
        self.call_from_thread(self.update_status, "Generating Emails...")
        try:
            self.outreach.generate_emails(limit=10)
        except Exception as e:
            self.call_from_thread(
                self.write_log, f"Email generation failed: {e}", "error"
            )
        finally:
            self.call_from_thread(self.update_status, "Idle")
            self.call_from_thread(self.refresh_stats)

    @work(exclusive=True, thread=True)
    def action_send_emails(self) -> None:
        """Send pending emails"""
        self.call_from_thread(self.update_status, "Sending Emails...")
        try:
            self.email_sender.send_pending_emails(limit=5)
        except Exception as e:
            self.call_from_thread(self.write_log, f"Email sending failed: {e}", "error")
        finally:
            self.call_from_thread(self.update_status, "Idle")
            self.call_from_thread(self.refresh_stats)

    def action_review_emails(self) -> None:
        """Open email review screen"""
        self.push_screen(ReviewScreen(self.repo), lambda _: self.refresh_stats())


if __name__ == "__main__":
    app = WebContractorTUI()
    app.run()
