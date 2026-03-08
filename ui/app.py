"""Web Contractor - Textual TUI Application with Performance Optimizations"""

import json
from typing import Dict, List

import click
from dotenv import load_dotenv
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen, Screen
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    RichLog,
    Static,
)
from textual import work

from core.discovery import PlaywrightScraper
from core.email import EmailSender
from core.db_peewee import (
    init_db, close_db,
    save_bucket, get_all_buckets,
    save_config, get_config, get_emails_needing_review,
    update_email_content, delete_email, mark_email_sent,
)
from core.outreach import Outreach

load_dotenv()


class ReviewScreen(Screen):
    """Screen for reviewing generated emails"""

    BINDINGS = [
        Binding("escape", "app.pop_screen", "Back"),
        Binding("a", "approve_selected", "Approve & Send"),
        Binding("e", "edit_selected", "Edit"),
        Binding("r", "refine_email", "AI Rewrite"),
        Binding("d", "delete_selected", "Delete"),
    ]

    def __init__(self):
        super().__init__()
        self.selected_email = None
        self.emails = []

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
        self.emails = get_emails_needing_review()
        for i, email in enumerate(self.emails):
            table.add_row(
                email["business_name"], email["subject"], key=str(email["id"])
            )

        if not self.emails:
            self.query_one("#email-details").update("No emails pending review.")
            self.selected_email = None
        else:
            if self.selected_email:
                new_data = next(
                    (e for e in self.emails if e["id"] == self.selected_email["id"]),
                    None,
                )
                self.selected_email = new_data if new_data else self.emails[0]
            else:
                self.selected_email = self.emails[0]
            
            for idx, email in enumerate(self.emails):
                if email["id"] == self.selected_email["id"]:
                    table.move_cursor(row=idx)
                    break
            
            self.update_detail_view()

    def on_data_table_row_selected(self, event: DataTable.RowSelected):
        if event.row_key.value is None:
            return
        try:
            email_id = int(event.row_key.value)
            self.selected_email = next(
                (e for e in self.emails if e["id"] == email_id), None
            )
            if self.selected_email:
                self.update_detail_view()
        except (ValueError, TypeError):
            self.notify("Invalid row selection", severity="error")

    def update_detail_view(self):
        if not self.selected_email:
            self.query_one("#email-details").update("No email selected.")
            return
        content = f"[b]To:[/b] {self.selected_email.get('email', 'N/A')}\n"
        content += f"[b]Subject:[/b] {self.selected_email['subject']}\n\n"

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

    @work(exclusive=True, thread=True)
    async def action_approve_selected(self):
        """Approve and immediately send the email"""
        if not self.selected_email:
            return

        email_id = self.selected_email["id"]
        to_email = self.selected_email.get("email")
        subject = self.selected_email["subject"]
        body = self.selected_email["body"]

        if not to_email:
            self.app.call_from_thread(self.app.notify, "No email address found for this lead!", severity="error")
            return

        self.app.call_from_thread(self.app.notify, f"Sending email to {self.selected_email['business_name']}...")

        success = self.app.email_sender.send_email(to_email, subject, body)

        if success:
            mark_email_sent(email_id, True)
            self.app.call_from_thread(
                self.app.notify,
                f"Email sent to {self.selected_email['business_name']}",
                severity="information",
            )
        else:
            mark_email_sent(email_id, False, "SMTP send failed")
            self.app.call_from_thread(
                self.app.notify,
                f"Failed to send email to {self.selected_email['business_name']}",
                severity="error",
            )

        self.app.call_from_thread(self.refresh_emails)

    def action_delete_selected(self):
        if self.selected_email:
            delete_email(self.selected_email["id"])
            self.notify(
                f"Deleted email for {self.selected_email['business_name']}",
                severity="error",
            )
            self.refresh_emails()

    def action_edit_selected(self):
        """Edit email using system default editor (e.g. nano)"""
        if not self.selected_email:
            return

        initial_content = (
            f"Subject: {self.selected_email['subject']}\n\n"
            f"{self.selected_email['body']}"
        )

        with self.app.suspend():
            new_content = click.edit(text=initial_content, extension=".txt")

        if new_content:
            if "\n\n" in new_content:
                subject_part, body = new_content.split("\n\n", 1)
                subject = subject_part.replace("Subject: ", "").strip()
            else:
                subject = self.selected_email["subject"]
                body = new_content

            update_email_content(self.selected_email["id"], subject, body)
            self.notify("Email updated via External Editor")
            self.refresh_emails()

    @work(exclusive=True, thread=True)
    async def action_refine_email(self):
        """Reintegrate AI refinement with a prompt"""
        if not self.selected_email:
            return

        refine_modal = RefineEmailModal()
        instructions = await self.app.push_screen_wait(refine_modal)

        if instructions:
            self.app.call_from_thread(self.app.notify, "AI is refining the email...")
            result = self.app.outreach.refine_email_ollama(
                self.selected_email["subject"], self.selected_email["body"], instructions
            )

            if result:
                update_email_content(
                    self.selected_email["id"], result["subject"], result["body"]
                )
                self.app.call_from_thread(self.app.notify, "AI refinement complete!")
                self.app.call_from_thread(self.refresh_emails)


class RefineEmailModal(ModalScreen):
    """Modal for entering AI refinement instructions"""
    
    MAX_INSTRUCTIONS_LENGTH = 500  

    def compose(self) -> ComposeResult:
        with Vertical(id="refine-container"):
            yield Label("AI Refinement Instructions")
            yield Label(
                "e.g. 'Make it shorter', 'Mention my portfolio', 'Be more formal'"
            )
            yield Input(placeholder="Enter instructions...", id="refine-input", max_length=self.MAX_INSTRUCTIONS_LENGTH)
            with Horizontal(id="refine-buttons"):
                yield Button("Refine", variant="success", id="refine-btn")
                yield Button("Cancel", variant="error", id="cancel-btn")

    def on_mount(self) -> None:
        self.query_one("#refine-input").focus()

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "refine-btn":
            instructions = self.query_one("#refine-input", Input).value
            if instructions and len(instructions.strip()) > 0:
                if len(instructions) > self.MAX_INSTRUCTIONS_LENGTH:
                    self.notify(f"Instructions too long (max {self.MAX_INSTRUCTIONS_LENGTH} chars)", severity="error")
                    return
                self.dismiss(instructions.strip())
            else:
                self.notify("Please enter some instructions", severity="warning")
        else:
            self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted):
        if event.value and len(event.value.strip()) > 0:
            if len(event.value) > self.MAX_INSTRUCTIONS_LENGTH:
                self.notify(f"Instructions too long (max {self.MAX_INSTRUCTIONS_LENGTH} chars)", severity="error")
                return
            self.dismiss(event.value.strip())
        else:
            self.notify("Please enter some instructions", severity="warning")


class MarketReviewScreen(Screen):
    """Screen for reviewing market expansion suggestions"""

    def __init__(self, suggestions: List[Dict]):
        super().__init__()
        self.suggestions = suggestions

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
        try:
            if "new_categories" in s:
                bucket_name = s.get("bucket_name")
                buckets = get_all_buckets()
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

                    geo_focus = get_config("geographic_focus") or {}
                    if "expanded" not in geo_focus:
                        geo_focus["expanded"] = {"cities": []}
                    geo_focus["expanded"]["cities"] = list(
                        set(
                            geo_focus["expanded"].get("cities", [])
                            + s.get("new_cities", [])
                        )
                    )
                    save_config("geographic_focus", geo_focus)

                    segments = bucket.get("geographic_segments", [])
                    if isinstance(segments, str):
                        try:
                            segments = json.loads(segments)
                        except json.JSONDecodeError:
                            self.notify("Invalid geographic_segments JSON, resetting", severity="error")
                            segments = []
                    if "expanded" not in segments:
                        segments.append("expanded")
                        bucket["geographic_segments"] = segments

                    save_bucket(bucket)
                    self.notify("Market expansion applied successfully", severity="information")
            else:
                s["geographic_segments"] = ["tier_1_metros"]
                s["conversion_probability"] = 0.5
                s["monthly_target"] = 100
                save_bucket(s)
                self.notify("New bucket created successfully", severity="information")
        except Exception as e:
            self.notify(f"Failed to apply suggestion: {type(e).__name__}", severity="error")


class WebContractorTUI(App):
    """Web Contractor Terminal User Interface with Performance Optimizations"""

    CSS = """
    Screen {
        background: $surface;
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

    /* Refine Modal CSS */
    #refine-container {
        padding: 1 2;
        background: $surface;
        border: thick $primary;
        width: 60;
        height: auto;
        align: center middle;
    }

    #refine-buttons {
        height: 3;
        align: center middle;
        margin-top: 1;
    }
    """

    BINDINGS = [
        Binding("d", "run_discovery", "Discovery"),
        Binding("x", "expand_markets", "Expand Markets"),
        Binding("a", "run_audit", "Audit"),
        Binding("g", "generate_emails", "Generate Emails"),
        Binding("v", "review_emails", "Review"),
        Binding("r", "refresh_all", "Refresh All"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self):
        super().__init__()

        init_db()

        self.discovery = PlaywrightScraper(logger=self.write_log)
        self.outreach = Outreach(logger=self.write_log)
        self.email_sender = EmailSender(logger=self.write_log)

    def compose(self) -> ComposeResult:
        """Create child widgets"""
        yield Header()

        yield Label("System Status: Idle", id="status-label")

        with Container(id="log-container"):
            yield RichLog(id="activity-log", markup=True)

        yield Footer()

    def on_mount(self) -> None:
        """Initialize UI on mount"""
        self.title = "Web Contractor"
        self.sub_title = "Lead Discovery & Outreach Automation"
        self.write_log("Web Contractor initialized", "success")
        self.write_log(
            "Press [d] Discovery, [a] Audit, [g] Generate, [v] Review, [s] Send, [q] Quit",
            "info",
        )

    def on_unmount(self) -> None:
        """Cleanup resources on app exit"""
        try:
            close_db()
        except Exception:
            pass  

    def write_log(self, message: str, style: str = ""):
        """Write to activity log"""
        log_widget = self.query_one("#activity-log", RichLog)
        if style == "success":
            log_widget.write(f"[green][/green] {message}")
        elif style == "error":
            log_widget.write(f"[red][/red] {message}")
        elif style == "info":
            log_widget.write(f"[cyan][/cyan] {message}")
        else:
            log_widget.write(message)

    def update_status(self, status: str = "Idle"):
        """Update status label"""
        sl = self.query_one("#status-label", Label)
        sl.update(f"System Status: {status}")

    def _audit_progress_callback(self, current: int, total: int, business_name: str):
        """Callback for audit progress updates (called from worker thread)"""
        self.call_from_thread(
            self.write_log,
            f"Progress: [{current}/{total}] Auditing {business_name}",
            "info",
        )

    def _email_gen_progress_callback(
        self, current: int, total: int, business_name: str
    ):
        """Callback for email generation progress updates (called from worker thread)"""
        self.call_from_thread(
            self.write_log,
            f"Progress: [{current}/{total}] Generating email for {business_name}",
            "info",
        )

    @work(exclusive=True, thread=True)
    def action_expand_markets(self) -> None:
        """Discover new market buckets and expansions"""
        self.call_from_thread(self.update_status, "Expanding Markets...")
        try:
            suggestions = []
            new_buckets = self.discovery.discover_new_buckets()
            if isinstance(new_buckets, list):
                suggestions.extend(new_buckets)

            for bucket in self.discovery.buckets:
                exp = self.discovery.expand_bucket(bucket["name"])
                if isinstance(exp, dict):
                    exp["bucket_name"] = bucket["name"]
                    suggestions.append(exp)

            if suggestions:
                self.call_from_thread(self.show_market_review, suggestions)
            else:
                self.call_from_thread(self.write_log, "No new market suggestions found.", "info")

        except Exception as e:
            self.call_from_thread(self.write_log, f"Market expansion failed: {e}", "error")
        finally:
            self.call_from_thread(self.update_status, "Idle")

    def show_market_review(self, suggestions: List[Dict]):
        self.push_screen(MarketReviewScreen(suggestions))

    @work(exclusive=True, thread=True)
    def action_run_discovery(self) -> None:
        """Run discovery pipeline (Stage 0 + Stage A)"""
        self.call_from_thread(self.update_status, "Running Discovery...")
        try:
            self.discovery.run(max_queries=None)
        except Exception as e:
            self.call_from_thread(self.write_log, f"Discovery failed: {e}", "error")
        finally:
            self.call_from_thread(self.update_status, "Idle")

    @work(exclusive=True, thread=True)
    def action_run_audit(self) -> None:
        """Run audit pipeline (Stage B)"""
        self.call_from_thread(self.update_status, "Auditing Leads...")
        try:
            self.outreach.audit_leads(
                limit=20,
                progress_callback=self._audit_progress_callback,
            )
        except Exception as e:
            self.call_from_thread(self.write_log, f"Audit failed: {e}", "error")
        finally:
            self.call_from_thread(self.update_status, "Idle")

    @work(exclusive=True, thread=True)
    def action_generate_emails(self) -> None:
        """Generate emails (Stage C)"""
        self.call_from_thread(self.update_status, "Generating Emails...")
        try:
            self.outreach.generate_emails(
                limit=20,
                progress_callback=self._email_gen_progress_callback,
            )
        except Exception as e:
            self.call_from_thread(self.write_log, f"Email generation failed: {e}", "error")
        finally:
            self.call_from_thread(self.update_status, "Idle")

    def action_review_emails(self) -> None:
        """Open email review screen"""
        self.push_screen(ReviewScreen())


if __name__ == "__main__":
    app = WebContractorTUI()
    app.run()
