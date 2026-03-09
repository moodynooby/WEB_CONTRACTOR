"""Web Contractor - Simplified TUI Application"""

import json
from typing import Callable, Dict, Iterable, List, Optional

import click
from dotenv import load_dotenv
from textual.app import App, ComposeResult, SystemCommand
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
    Select,
    Static,
    RichLog
)
from textual import work

from core.discovery import PlaywrightScraper
from core.email import EmailSender
from core.db_peewee import (
    init_db, close_db,
    save_bucket, get_all_buckets,
    save_config, get_config, get_emails_for_review,
    update_email_content, delete_email, mark_email_sent,
    get_query_performance_stats,
    get_top_performing_queries, get_worst_performing_queries,
    get_overall_efficiency_metrics,
    Lead, Audit, EmailCampaign, QueryPerformance,
)
from core.outreach import Outreach

load_dotenv()


def _safe_truncate(value: Optional[str], max_length: int) -> str:
    """Safely truncate a string value, handling None gracefully."""
    if value is None:
        return "N/A"
    return str(value)[:max_length]

class DatabaseBrowserScreen(Screen):
    """Simplified screen for browsing database tables"""

    BINDINGS = [
        Binding("escape", "back", "Back"),
        Binding("r", "refresh", "Refresh"),
        Binding("t", "change_table", "Table"),
    ]

    TABLE_TYPES: List[tuple[str, str]] = [
        ("buckets", "🪣 Buckets"),
        ("leads", "🎯 Leads"),
        ("emails", "📧 Emails"),
        ("audits", "🔍 Audits"),
        ("queries", "⚡ Queries"),
    ]

    def __init__(self):
        super().__init__()
        self.current_table: str = "leads"
        self.filter_status: str = "all"

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="db-browser-container"):
            with Horizontal(id="db-controls"):
                yield Select(
                    [(name, key) for key, name in self.TABLE_TYPES],
                    value=self.current_table,
                    allow_blank=False,
                    id="table-selector"
                )
                yield Select(
                    [("All", "all"), ("Pending", "pending"), ("Qualified", "qualified"), ("Sent", "sent")],
                    value="all",
                    allow_blank=False,
                    id="filter-selector"
                )
                yield Static(f"Table: {self._get_table_display_name()}", id="table-info")

            yield DataTable(id="data-table")
            yield Static("", id="table-status")

        yield Footer()

    def _get_table_display_name(self) -> str:
        for key, name in self.TABLE_TYPES:
            if key == self.current_table:
                return str(name)
        return self.current_table

    def on_mount(self) -> None:
        self._setup_table()
        self._refresh_data()

    def _setup_table(self):
        """Setup DataTable columns based on current table type."""
        table = self.query_one("#data-table", DataTable)
        table.clear()

        columns_map = {
            "buckets": ("ID", "Name", "Priority", "Queries", "Results", "Limit", "Count"),
            "leads": ("ID", "Business", "Category", "Location", "Email", "Status", "Score"),
            "emails": ("ID", "Business", "Subject", "Status", "Sent At"),
            "audits": ("ID", "Business", "Score", "Qualified", "Issues", "Date"),
            "queries": ("ID", "Bucket", "Query", "City", "Active", "Exec", "Success %"),
        }
        table.add_columns(*columns_map.get(self.current_table, ("ID", "Data")))
        table.cursor_type = "row"

    def _refresh_data(self):
        """Refresh data based on current table and filter."""
        table = self.query_one("#data-table", DataTable)
        table.clear()

        data_getters = {
            "buckets": self._load_buckets,
            "leads": self._load_leads,
            "emails": self._load_emails,
            "audits": self._load_audits,
            "queries": self._load_queries,
        }
        getter = data_getters.get(self.current_table)
        if getter:
            getter()

        count = len(table.rows)
        self.query_one("#table-status", Static).update(
            f"[dim]Showing {count} items | [cyan]↑/↓[/cyan] navigate | [cyan]Enter[/cyan] view | [cyan]esc[/cyan] back[/dim]"
        )

    def _load_buckets(self):
        table = self.query_one("#data-table", DataTable)
        for bucket in get_all_buckets():
            table.add_row(
                str(bucket.get('id', 'N/A')),
                bucket.get('name', 'Unknown'),
                str(bucket.get('priority', 1)),
                str(bucket.get('max_queries', 5)),
                str(bucket.get('max_results', 2)),
                str(bucket.get('daily_email_limit', 500)),
                str(bucket.get('daily_email_count', 0)),
            )

    def _load_leads(self):
        table = self.query_one("#data-table", DataTable)
        query = Lead.select().order_by(Lead.created_at.desc()).limit(100)
        if self.filter_status != "all":
            query = query.where(Lead.status == self.filter_status)
        for lead in query:
            lead_dict = lead.to_dict()
            status_style = "green" if lead_dict.get('status') == 'qualified' else "yellow" if lead_dict.get('status') == 'pending_audit' else "default"
            table.add_row(
                str(lead_dict.get('id', 'N/A')),
                _safe_truncate(lead_dict.get('business_name'), 25),
                _safe_truncate(lead_dict.get('category'), 15),
                _safe_truncate(lead_dict.get('location'), 15),
                _safe_truncate(lead_dict.get('email'), 20),
                f"[{status_style}]{lead_dict.get('status', 'pending')}[/{status_style}]",
                f"{lead_dict.get('quality_score', 0):.2f}",
            )

    def _load_emails(self):
        table = self.query_one("#data-table", DataTable)
        query = EmailCampaign.select().order_by(
            EmailCampaign.sent_at.desc() if EmailCampaign.sent_at else EmailCampaign.created_at.desc()
        ).limit(100)
        if self.filter_status != "all":
            query = query.where(EmailCampaign.status == self.filter_status)
        for email in query:
            lead = email.lead
            business_name = lead.business_name if lead else 'N/A'
            sent_at = email.sent_at.strftime('%Y-%m-%d') if email.sent_at else 'N/A'
            status_style = "green" if email.status == 'sent' else "yellow" if email.status == 'pending' else "red"
            table.add_row(
                str(email.id),
                _safe_truncate(business_name, 25),
                _safe_truncate(email.subject, 30),
                f"[{status_style}]{email.status}[/{status_style}]",
                sent_at,
            )

    def _load_audits(self):
        table = self.query_one("#data-table", DataTable)
        for audit in Audit.select().order_by(Audit.audit_date.desc()).limit(100):
            lead = audit.lead
            business_name = lead.business_name if lead else 'N/A'
            issues_count = len(audit.get_issues())
            qualified_str = "[green]✓[/green]" if audit.qualified else "[red]✗[/red]"
            table.add_row(
                str(audit.id),
                _safe_truncate(business_name, 25),
                str(audit.score),
                qualified_str,
                str(issues_count),
                audit.audit_date.strftime('%Y-%m-%d'),
            )

    def _load_queries(self):
        table = self.query_one("#data-table", DataTable)
        for qp in QueryPerformance.select().order_by(QueryPerformance.total_executions.desc()).limit(100):
            qp_dict = qp.to_dict()
            success_rate = 0
            if qp.total_executions > 0:
                success_rate = (qp.total_leads_found / qp.total_executions) * 100
            active_str = "[green]✓[/green]" if qp.is_active else "[red]✗[/red]"
            table.add_row(
                str(qp_dict.get('id', 'N/A')),
                _safe_truncate(qp_dict.get('bucket'), 12),
                _safe_truncate(qp_dict.get('query_pattern'), 20),
                _safe_truncate(qp_dict.get('city'), 12),
                active_str,
                str(qp_dict.get('total_executions', 0)),
                f"[green]{success_rate:.1f}%[/green]" if success_rate > 50 else f"[red]{success_rate:.1f}%[/red]",
            )

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "table-selector":
            self.current_table = str(event.value)
            self._setup_table()
            self._refresh_data()
        elif event.select.id == "filter-selector":
            self.filter_status = str(event.value)
            self._refresh_data()

    def action_refresh(self):
        self._refresh_data()
        self.notify("Data refreshed")

    def action_change_table(self):
        self.query_one("#table-selector", Select).focus()

    def action_back(self):
        self.app.pop_screen()

    def on_data_table_row_selected(self, event: DataTable.RowSelected):
        self.notify("Row selected", timeout=1)


# REVIEW SCREEN (Simplified)

class ReviewScreen(Screen):
    """Simplified screen for reviewing generated emails"""

    BINDINGS = [
        Binding("escape", "app.pop_screen", "Back"),
        Binding("a", "approve_selected", "Approve"),
        Binding("e", "edit_selected", "Edit"),
        Binding("r", "refine_email", "Rewrite"),
        Binding("d", "delete_selected", "Delete"),
        Binding("j", "next_email", "Next"),
        Binding("k", "prev_email", "Prev"),
        Binding("down", "next_email", "Next"),
        Binding("up", "prev_email", "Prev"),
    ]

    def __init__(self):
        super().__init__()
        self.selected_email = None
        self.emails = []
        self.current_index = 0

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="review-container"):
            yield Static("", id="email-counter")
            with Horizontal(id="review-split"):
                with Vertical(id="email-list-panel"):
                    yield Label("[bold]Pending Review[/bold]")
                    yield DataTable(id="email-table")
                with Vertical(id="email-detail-panel"):
                    yield Static("", id="email-details")
            with Horizontal(id="review-actions"):
                yield Button("[green]✓[/green] Approve & Send", variant="success", id="approve-btn")
                yield Button("[cyan]✎[/cyan] Edit", variant="primary", id="edit-btn")
                yield Button("[yellow]✦[/yellow] AI Rewrite", variant="warning", id="rewrite-btn")
                yield Button("[red]✗[/red] Delete", variant="error", id="delete-btn")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#email-table", DataTable)
        table.add_columns("Business", "Subject")
        table.cursor_type = "row"
        self.refresh_emails()

    def refresh_emails(self):
        table = self.query_one("#email-table", DataTable)
        table.clear()
        self.emails = get_emails_for_review()
        for i, email in enumerate(self.emails):
            table.add_row(
                email["business_name"], email["subject"], key=str(email["id"])
            )

        if not self.emails:
            self.query_one("#email-details", Static).update(
                "[dim]No emails pending review.[/dim]\n\n[cyan]Run 'Generate Emails' from dashboard to create outreach emails.[/cyan]"
            )
            self.query_one("#email-counter", Static).update("")
            self.selected_email = None
            return

        if self.selected_email:
            new_data = next((e for e in self.emails if e["id"] == self.selected_email["id"]), None)
            self.selected_email = new_data if new_data else self.emails[0]
        else:
            self.selected_email = self.emails[0] if self.emails else None

        total = len(self.emails)
        current = self.current_index + 1 if self.emails else 0
        self.query_one("#email-counter", Static).update(
            f"[bold]Email {current} of {total}[/bold]"
        )

        for idx, email in enumerate(self.emails):
            if email["id"] == self.selected_email["id"]:
                table.move_cursor(row=idx)
                self.current_index = idx
                break

        self.update_detail_view()

    def on_data_table_row_selected(self, event: DataTable.RowSelected):
        if event.row_key.value is None:
            return
        try:
            email_id = int(event.row_key.value)
            self.selected_email = next((e for e in self.emails if e["id"] == email_id), None)
            if self.selected_email:
                for idx, email in enumerate(self.emails):
                    if email["id"] == email_id:
                        self.current_index = idx
                        break
                self.update_detail_view()
                self._update_counter()
        except (ValueError, TypeError):
            self.notify("Invalid selection", severity="error")

    def _update_counter(self):
        total = len(self.emails)
        current = self.current_index + 1
        self.query_one("#email-counter", Static).update(f"[bold]Email {current} of {total}[/bold]")

    def update_detail_view(self):
        if not self.selected_email:
            self.query_one("#email-details", Static).update("[dim]No email selected.[/dim]")
            return

        email = self.selected_email
        content = f"""[bold][cyan]To:[/cyan][/bold] {email.get('email', 'N/A')}
[bold][cyan]Subject:[/cyan][/bold] {email['subject']}
"""
        alt_comm = []
        if email.get("contact_form_url"):
            alt_comm.append(f"  [dim]• Form:[/dim] {email['contact_form_url']}")
        social = email.get("social_links", {})
        for plat, link in social.items():
            alt_comm.append(f"  [dim]• {plat.capitalize()}:[/dim] {link}")

        if alt_comm:
            content += "\n[bold]Other Channels:[/bold]\n" + "\n".join(alt_comm)

        content += f"\n[bold][green]Message:[/green][/bold]\n{email['body']}"
        self.query_one("#email-details", Static).update(content)

    def action_next_email(self):
        if self.emails and self.current_index < len(self.emails) - 1:
            self.current_index += 1
            self.selected_email = self.emails[self.current_index]
            table = self.query_one("#email-table", DataTable)
            table.move_cursor(row=self.current_index)
            self.update_detail_view()
            self._update_counter()

    def action_prev_email(self):
        if self.emails and self.current_index > 0:
            self.current_index -= 1
            self.selected_email = self.emails[self.current_index]
            table = self.query_one("#email-table", DataTable)
            table.move_cursor(row=self.current_index)
            self.update_detail_view()
            self._update_counter()

    @work(exclusive=True, thread=True)
    async def action_approve_selected(self):
        if not self.selected_email:
            return

        email_id = self.selected_email["id"]
        to_email = self.selected_email.get("email")
        subject = self.selected_email["subject"]
        body = self.selected_email["body"]

        if not to_email:
            self.app.call_from_thread(self.app.notify, "No email address!", severity="error")
            return

        self.app.call_from_thread(self.app.notify, f"Sending to {self.selected_email['business_name']}...")
        success = self.app.email_sender.send_email(to_email, subject, body)

        if success:
            mark_email_sent(email_id, True)
            self.app.call_from_thread(self.app.notify, "✓ Email sent!", severity="information")
        else:
            mark_email_sent(email_id, False, "SMTP failed")
            self.app.call_from_thread(self.app.notify, "✗ Send failed", severity="error")

        self.app.call_from_thread(self.refresh_emails)

    def action_delete_selected(self):
        if self.selected_email:
            delete_email(self.selected_email["id"])
            self.notify(f"Deleted: {self.selected_email['business_name']}", severity="error")
            self.refresh_emails()

    def action_edit_selected(self):
        if not self.selected_email:
            return

        initial_content = f"Subject: {self.selected_email['subject']}\n\n{self.selected_email['body']}"
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
            self.notify("✓ Email updated")
            self.refresh_emails()

    @work(exclusive=True, thread=True)
    async def action_refine_email(self):
        if not self.selected_email:
            return

        refine_modal = RefineEmailModal()
        instructions = await self.app.push_screen_wait(refine_modal)

        if instructions:
            self.app.call_from_thread(self.app.notify, "AI refining...")
            result = self.app.outreach.refine_email_ollama(
                self.selected_email["subject"], self.selected_email["body"], instructions
            )

            if result:
                update_email_content(self.selected_email["id"], result["subject"], result["body"])
                self.app.call_from_thread(self.app.notify, "✓ AI rewrite complete!")
                self.app.call_from_thread(self.refresh_emails)


class RefineEmailModal(ModalScreen):
    """Modal for entering AI refinement instructions"""

    MAX_INSTRUCTIONS_LENGTH = 500

    def compose(self) -> ComposeResult:
        with Vertical(id="refine-container"):
            yield Label("[bold]AI Refinement Instructions[/bold]")
            yield Label("[dim]e.g. 'Make it shorter', 'Mention portfolio', 'Be more formal'[/dim]")
            yield Input(placeholder="Enter instructions...", id="refine-input", max_length=self.MAX_INSTRUCTIONS_LENGTH)
            with Horizontal(id="refine-buttons"):
                yield Button("Refine", variant="success", id="refine-btn")
                yield Button("Cancel", variant="error", id="cancel-btn")

    def on_mount(self) -> None:
        self.query_one("#refine-input", Input).focus()

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "refine-btn":
            instructions = self.query_one("#refine-input", Input).value
            if instructions and len(instructions.strip()) > 0:
                if len(instructions) > self.MAX_INSTRUCTIONS_LENGTH:
                    self.notify(f"Max {self.MAX_INSTRUCTIONS_LENGTH} chars", severity="error")
                    return
                self.dismiss(instructions.strip())
            else:
                self.notify("Please enter instructions", severity="warning")
        else:
            self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted):
        if event.value and len(event.value.strip()) > 0:
            if len(event.value) > self.MAX_INSTRUCTIONS_LENGTH:
                self.notify(f"Max {self.MAX_INSTRUCTIONS_LENGTH} chars", severity="error")
                return
            self.dismiss(event.value.strip())
        else:
            self.notify("Please enter instructions", severity="warning")


# MARKET REVIEW SCREEN

class MarketReviewScreen(Screen):
    """Screen for reviewing market expansion suggestions"""

    BINDINGS = [
        Binding("escape", "dismiss", "Done"),
        Binding("a", "approve_selected", "Approve"),
        Binding("r", "reject_selected", "Reject"),
    ]

    def __init__(self, suggestions: List[Dict]):
        super().__init__()
        self.suggestions = suggestions

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="market-review-container"):
            yield Label("[bold]LLM Market Expansion Suggestions[/bold]")
            yield Static("[dim]Review and approve new buckets or expansions[/dim]", id="market-status")
            yield DataTable(id="market-table")
            with Horizontal(id="market-actions"):
                yield Button("✓ Approve", variant="success", id="approve-market")
                yield Button("✗ Reject", variant="error", id="reject-market")
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
            if table.cursor_row is not None and table.cursor_row < len(self.suggestions):
                idx = table.cursor_row
                suggestion = self.suggestions[idx]
                self.apply_suggestion(suggestion)
                self.suggestions.pop(idx)
                self.refresh_table()
                self.notify("✓ Suggestion applied", severity="information")
        elif event.button.id == "reject-market":
            table = self.query_one("#market-table", DataTable)
            if table.cursor_row is not None and table.cursor_row < len(self.suggestions):
                idx = table.cursor_row
                self.suggestions.pop(idx)
                self.refresh_table()
                self.notify("✗ Suggestion rejected", severity="error")

    def action_approve_selected(self):
        table = self.query_one("#market-table", DataTable)
        if table.cursor_row is not None and table.cursor_row < len(self.suggestions):
            idx = table.cursor_row
            suggestion = self.suggestions[idx]
            self.apply_suggestion(suggestion)
            self.suggestions.pop(idx)
            self.refresh_table()
            self.notify("✓ Suggestion applied", severity="information")

    def action_reject_selected(self):
        table = self.query_one("#market-table", DataTable)
        if table.cursor_row is not None and table.cursor_row < len(self.suggestions):
            idx = table.cursor_row
            self.suggestions.pop(idx)
            self.refresh_table()
            self.notify("✗ Suggestion rejected", severity="error")

    def apply_suggestion(self, s: Dict):
        try:
            if "new_categories" in s:
                bucket_name = s.get("bucket_name")
                buckets = get_all_buckets()
                bucket = next((b for b in buckets if b["name"] == bucket_name), None)
                if bucket:
                    new_cats = list(set(bucket.get("categories", []) + s.get("new_categories", [])))
                    new_pats = list(set(bucket.get("search_patterns", []) + s.get("new_patterns", [])))
                    bucket["categories"] = new_cats
                    bucket["search_patterns"] = new_pats

                    geo_focus = get_config("geographic_focus") or {}
                    if "expanded" not in geo_focus:
                        geo_focus["expanded"] = {"cities": []}
                    geo_focus["expanded"]["cities"] = list(
                        set(geo_focus["expanded"].get("cities", []) + s.get("new_cities", []))
                    )
                    save_config("geographic_focus", geo_focus)

                    segments = bucket.get("geographic_segments", [])
                    if isinstance(segments, str):
                        try:
                            segments = json.loads(segments)
                        except json.JSONDecodeError:
                            segments = []
                    if "expanded" not in segments:
                        segments.append("expanded")
                        bucket["geographic_segments"] = segments

                    save_bucket(bucket)
                    self.notify("✓ Market expansion applied", severity="information")
            else:
                s["geographic_segments"] = ["tier_1_metros"]
                s["conversion_probability"] = 0.5
                s["monthly_target"] = 100
                save_bucket(s)
                self.notify("✓ New bucket created", severity="information")
        except Exception as e:
            self.notify(f"Failed: {e}", severity="error")


# QUERY PERFORMANCE SCREEN (Simplified)

class QueryPerformanceScreen(Screen):
    """Simplified screen for viewing query performance"""

    BINDINGS = [
        Binding("escape", "app.pop_screen", "Back"),
        Binding("r", "refresh_stats", "Refresh"),
    ]

    def __init__(self):
        super().__init__()
        self.selected_query = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="query-perf-container"):
            yield Label("[bold]Query Performance Dashboard[/bold]", id="perf-title")

            with Horizontal(id="stats-row"):
                yield Static("Loading...", id="perf-stats")
                yield Static("Loading...", id="efficiency-stats")

            with Horizontal(id="tables-row"):
                with Vertical(id="top-section"):
                    yield Label("[green]Top Performing Queries[/green]")
                    yield DataTable(id="top-table")
                with Vertical(id="bottom-section"):
                    yield Label("[red]Underperforming Queries[/red]")
                    yield DataTable(id="bottom-table")

            with Horizontal(id="actions-row"):
                yield Button("Refresh", variant="primary", id="refresh-btn")
                yield Button("Done", variant="default", id="done-btn")
        yield Footer()

    def on_mount(self) -> None:
        top_table = self.query_one("#top-table", DataTable)
        top_table.add_columns("Bucket", "Query", "City", "Success %", "Exec")
        top_table.cursor_type = "row"

        bottom_table = self.query_one("#bottom-table", DataTable)
        bottom_table.add_columns("Bucket", "Query", "City", "Success %", "Exec")
        bottom_table.cursor_type = "row"

        self.refresh_all()

    def refresh_all(self):
        self.refresh_stats_display()
        self.refresh_efficiency_display()
        self.refresh_top_bottom_tables()

    def refresh_stats_display(self):
        stats = get_query_performance_stats()
        stats_content = (
            f"[bold]Overview[/bold] | "
            f"Total: [cyan]{stats['total_queries']}[/cyan] | "
            f"Active: [green]{stats['active_queries']}[/green] | "
            f"Stale: [red]{stats['stale_queries']}[/red] | "
            f"Executions: {stats['total_executions']} | "
            f"Leads: {stats['total_leads_found']} | "
            f"Success Rate: [bold green]{stats['average_success_rate']}%[/bold green]"
        )
        self.query_one("#perf-stats", Static).update(stats_content)

    def refresh_efficiency_display(self):
        metrics = get_overall_efficiency_metrics()
        metrics_content = (
            f"[bold]Efficiency[/bold] | "
            f"Leads/Exec: [bold]{metrics['leads_per_execution']}[/bold] | "
            f"Save Rate: [bold green]{metrics['save_rate']}%[/bold green] | "
            f"Qualification: [bold]{metrics['qualification_rate']}%[/bold] | "
            f"Saved: {metrics['total_leads_saved']}/{metrics['total_leads_found']}"
        )
        self.query_one("#efficiency-stats", Static).update(metrics_content)

    def refresh_top_bottom_tables(self):
        top_table = self.query_one("#top-table", DataTable)
        top_table.clear()
        top_queries = get_top_performing_queries(limit=10, min_executions=2)
        for tq in top_queries:
            top_table.add_row(
                tq.get('bucket', 'Unknown'),
                tq.get('query_pattern', 'N/A'),
                tq.get('city', 'N/A'),
                f"[green]{tq.get('success_rate', 0)}%[/green]",
                str(tq.get('total_executions', 0)),
            )

        bottom_table = self.query_one("#bottom-table", DataTable)
        bottom_table.clear()
        bottom_queries = get_worst_performing_queries(limit=10, min_executions=2)
        for bq in bottom_queries:
            bottom_table.add_row(
                bq.get('bucket', 'Unknown'),
                bq.get('query_pattern', 'N/A'),
                bq.get('city', 'N/A'),
                f"[red]{bq.get('success_rate', 0)}%[/red]",
                str(bq.get('total_executions', 0)),
            )

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "done-btn":
            self.dismiss()
        elif event.button.id == "refresh-btn":
            self.refresh_all()
            self.notify("Statistics refreshed")

    def action_refresh_stats(self):
        self.refresh_all()
        self.notify("Statistics refreshed")


# ─────────────────────────────────────────────────────────────────────────────
# LOGS SCREEN
# ─────────────────────────────────────────────────────────────────────────────

class LogsScreen(Screen):
    """Screen for viewing live activity logs"""

    BINDINGS = [
        Binding("escape", "app.pop_screen", "Back"),
        Binding("c", "clear_logs", "Clear"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="logs-container"):
            yield Label("[bold]📋 Activity Logs[/bold]")
            yield RichLog(id="activity-log", markup=True, highlight=True)
            with Horizontal(id="logs-actions"):
                yield Button("Clear", variant="error", id="clear-btn")
                yield Button("Done", variant="primary", id="done-btn")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "done-btn":
            self.dismiss()
        elif event.button.id == "clear-btn":
            log_widget = self.query_one("#activity-log", RichLog)
            log_widget.clear()
            self.notify("Logs cleared")

    def action_clear_logs(self):
        log_widget = self.query_one("#activity-log", RichLog)
        log_widget.clear()
        self.notify("Logs cleared")


class WebContractorTUI(App):
    """Web Contractor - Simplified TUI for Lead Discovery & Outreach"""

    CSS = """
    Screen { background: $surface; }

    /* Dashboard Styles */
    #dashboard-container { padding: 1 2; }

    #dashboard-stats {
        height: auto;
        grid-size: 3 1;
        grid-gutter: 1;
        margin-bottom: 1;
    }

    .stat-card {
        background: $primary-background;
        border: solid $primary;
        padding: 1 2;
        height: auto;
        min-height: 6;
    }

    .stat-card.action { border: solid $accent; }
    .stat-card.progress { border: solid $success; }
    .stat-card.health { border: solid $warning; }

    /* Pipeline Controls */
    #pipeline-section {
        margin: 1 0;
        padding: 1;
        border: solid $primary;
    }

    #pipeline-visual {
        height: auto;
        margin: 1 0;
        text-align: center;
        color: $text-muted;
    }

    .pipeline-stage {
        display: block;
        padding: 0 1;
    }

    .pipeline-stage.active { background: $accent; color: $text; padding: 0 2; }
    .pipeline-stage.done { background: $success; color: $text; padding: 0 2; }
    .pipeline-stage.pending { color: $text-muted; }

    #pipeline-actions {
        height: auto;
        align: center middle;
        margin: 1 0;
    }

    #pipeline-actions Button {
        margin: 0 1;
        min-width: 12;
        max-width: 16;
    }

    /* Quick Stats Bar */
    #quick-stats {
        height: auto;
        margin: 1 0;
        padding: 1;
        background: $surface;
    }

    /* Status Bar */
    #status-bar {
        dock: bottom;
        height: 1;
        background: $primary-background;
        color: $text;
        padding: 0 2;
    }

    .status-running { color: $accent; }
    .status-idle { color: $text-muted; }
    .status-error { color: $error; }

    /* Review Screen */
    #review-container { padding: 1 2; height: 100%; }
    #email-counter { text-align: center; padding: 1; }
    #review-split { height: 1fr; }
    #email-list-panel { width: 40%; border: solid $primary; }
    #email-detail-panel { width: 60%; border: solid $primary; padding: 1; }
    #email-details { height: 1fr; overflow-y: scroll; }
    #review-actions { height: 3; align: center middle; }

    /* Logs Screen */
    #logs-container { padding: 1 2; height: 100%; }
    #activity-log { height: 1fr; border: solid $primary; margin: 1 0; padding: 1; }
    #logs-actions { height: 3; align: center middle; margin-top: 1; }

    /* Database Browser */
    #db-browser-container { padding: 1 2; height: 100%; }
    #db-controls { height: 3; margin-bottom: 1; }
    #table-selector { width: 30%; }
    #filter-selector { width: 25%; }
    #table-info { width: 45%; content-align: right middle; }
    #data-table { height: 1fr; }
    #table-status { height: 1; text-align: center; color: $text-muted; }

    /* Query Performance */
    #query-perf-container { padding: 1 2; height: 100%; }
    #perf-title { text-align: center; padding: 1; }
    #stats-row { height: auto; margin-bottom: 1; }
    #perf-stats, #efficiency-stats { padding: 1; width: 50%; border: solid $primary; }
    #tables-row { height: 1fr; }
    #top-section, #bottom-section { width: 50%; border: solid $primary; padding: 1; }
    #top-table, #bottom-table { height: 1fr; }
    #actions-row { height: 3; align: center middle; margin-top: 1; }

    /* Market Review */
    #market-review-container { padding: 1 2; height: 100%; }
    #market-table { height: 1fr; margin: 1 0; }
    #market-actions { height: 3; align: center middle; }

    /* Refine Modal */
    #refine-container {
        padding: 1 2;
        background: $surface;
        border: thick $primary;
        width: 60;
        height: auto;
        align: center middle;
    }
    #refine-buttons { height: 3; align: center middle; margin-top: 1; }

    /* Utility */
    .success { color: $success; }
    .error { color: $error; }
    .info { color: $accent; }
    .warning { color: $warning; }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit", show=True, priority=True),
        Binding("r", "refresh", "Refresh", show=True),
        Binding("ctrl+p", "command_palette", "Commands", show=False),
        Binding("d", "run_discovery", "Discovery", show=True),
        Binding("a", "run_audit", "Audit", show=True),
        Binding("g", "generate_emails", "Generate", show=True),
        Binding("v", "review_emails", "Review", show=True),
        Binding("b", "database_browser", "Database", show=True),
        Binding("p", "query_performance", "Perf", show=True),
        Binding("l", "show_logs", "Logs", show=True),
    ]

    def __init__(self):
        super().__init__()
        init_db()
        self.discovery = PlaywrightScraper(logger=self.write_log)
        self.outreach = Outreach(logger=self.write_log)
        self.email_sender = EmailSender(logger=self.write_log)
        self.current_operation: Optional[str] = None
        self.operation_progress: Optional[int] = None

    def compose(self) -> ComposeResult:
        yield Header()

        with Container(id="dashboard-container"):

            with Vertical(id="pipeline-section"):
                yield Static(self._get_pipeline_visual(), id="pipeline-visual")
                with Horizontal(id="pipeline-actions"):
                    yield Button("🔍 Discovery", variant="primary", id="discovery-btn")
                    yield Button("📊 Audit", variant="primary", id="audit-btn")
                    yield Button("📧 Generate", variant="primary", id="generate-btn")
                    yield Button("✅ Review", variant="success", id="review-btn")
                    yield Button("🚀 Send", variant="warning", id="send-btn")

            yield Static(self._get_quick_stats(), id="quick-stats")

        yield Static(self._get_status_bar(), id="status-bar")
        yield Footer()


    def _get_pipeline_visual(self) -> str:
        """Visual pipeline showing current state."""
        stages = [
            ("🔍", "Discovery", self.current_operation == "discovery"),
            ("📊", "Audit", self.current_operation == "audit"),
            ("📧", "Generate", self.current_operation == "generate"),
            ("✅", "Review", self.current_operation == "review"),
            ("🚀", "Send", self.current_operation == "send"),
        ]

        parts = []
        for icon, name, active in stages:
            if active:
                parts.append(f"[bold accent]{icon} {name}[/bold accent]")
            else:
                parts.append(f"[dim]{icon} {name}[/dim]")

        progress_str = f" ({self.operation_progress}%)" if self.operation_progress else ""
        return " → ".join(parts) + progress_str

    def _get_quick_stats(self) -> str:
        """Quick stats bar."""
        buckets = len(get_all_buckets())
        total_leads = Lead.select().count()
        total_emails = EmailCampaign.select().count()
        total_audits = Audit.select().count()

        return f"[dim]Buckets: {buckets} | Leads: {total_leads} | Audits: {total_audits} | Emails: {total_emails}[/dim]"

    def _get_status_bar(self) -> str:
        """Status bar showing current operation."""
        if self.current_operation:
            progress = f" ({self.operation_progress}%)" if self.operation_progress else ""
            return f"[bold accent]⚙ {self.current_operation.title()} Running{progress}[/bold accent] [dim]| Ctrl+C to cancel[/dim]"
        else:
            return "[dim]System Idle | Press 'd', 'a', 'g', 'v' for pipeline actions [/dim]"

    def on_mount(self) -> None:
        self.title = "Web Contractor"
        self.sub_title = "Lead Discovery & Outreach Automation"
        self.write_log("Initialized | [cyan]d[/cyan] Discovery [cyan]a[/cyan] Audit [cyan]g[/cyan] Generate [cyan]v[/cyan] Review ", "info")

    def on_unmount(self) -> None:
        try:
            close_db()
        except Exception:
            pass

    def write_log(self, message: str, style: str = ""):
        """Write log to console and RichLog widget if visible."""
        # Print to console
        import sys
        timestamp = __import__('datetime').datetime.now().strftime("%H:%M:%S")
        if style == "success":
            print(f"\033[92m[{timestamp}] ✓ {message}\033[0m", file=sys.stderr)
        elif style == "error":
            print(f"\033[91m[{timestamp}] ✗ {message}\033[0m", file=sys.stderr)
        elif style == "info":
            print(f"\033[96m[{timestamp}] ℹ {message}\033[0m", file=sys.stderr)
        else:
            print(f"[{timestamp}] {message}", file=sys.stderr)

        # Also write to logs screen if it exists
        try:
            if isinstance(self.screen, LogsScreen):
                log_widget = self.screen.query_one("#activity-log", RichLog)
                if style == "success":
                    log_widget.write(f"[green]✓[/green] {message}")
                elif style == "error":
                    log_widget.write(f"[red]✗[/red] {message}")
                elif style == "info":
                    log_widget.write(f"[cyan]ℹ[/cyan] {message}")
                else:
                    log_widget.write(message)
        except Exception:
            pass  # Screen may not have log widget or may not be active

    def _make_progress_callback(
        self, 
        operation: str, 
        notify_every: int = 5
    ) -> Callable[[int, int, str], None]:
        """Create a progress callback for any operation.
        
        Args:
            operation: Operation name (e.g., "Auditing", "Generating")
            notify_every: Show notification every N items
            
        Returns:
            Callback function: (current, total, item_name) -> None
        """
        def callback(current: int, total: int, item_name: str = "") -> None:
            progress = int((current / total) * 100) if total > 0 else 0
            self.call_from_thread(self.update_status, operation, operation.lower(), progress)
            if current % notify_every == 0 or current == total:
                self.call_from_thread(
                    self.notify, 
                    f"{operation}: {current}/{total} - {item_name}", 
                    timeout=2
                )
        return callback

    def update_status(self, status: str = "Idle", operation: Optional[str] = None, progress: Optional[int] = None):
        self.current_operation = operation
        self.operation_progress = progress
        self.query_one("#status-bar", Static).update(self._get_status_bar())
        self.query_one("#pipeline-visual", Static).update(self._get_pipeline_visual())
        if operation:
            self.sub_title = f"{operation.title()}..."
        else:
            self.sub_title = "Lead Discovery & Outreach Automation"

    def _refresh_dashboard(self):
        """Refresh dashboard stats."""
        try:
            self.query_one("#quick-stats", Static).update(self._get_quick_stats())
            self.query_one("#status-bar", Static).update(self._get_status_bar())
        except Exception:
            pass

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "discovery-btn":
            self.action_run_discovery()
        elif event.button.id == "audit-btn":
            self.action_run_audit()
        elif event.button.id == "generate-btn":
            self.action_generate_emails()
        elif event.button.id == "review-btn":
            self.action_review_emails()
        elif event.button.id == "send-btn":
            self.action_review_emails()

    def action_refresh(self):
        self._refresh_dashboard()
        self.notify("Dashboard refreshed")

    @work(exclusive=True, thread=True)
    def action_expand_markets(self) -> None:
        self.call_from_thread(self.update_status, "Expanding", "expand", None)
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
                self.call_from_thread(self.notify, "No new market suggestions", severity="information")
        except Exception as e:
            self.call_from_thread(self.notify, f"Expansion failed: {e}", severity="error")
        finally:
            self.call_from_thread(self.update_status, "Idle")

    def show_market_review(self, suggestions: List[Dict]):
        self.push_screen(MarketReviewScreen(suggestions))

    @work(exclusive=True, thread=True)
    def action_run_discovery(self) -> None:
        self.call_from_thread(self.update_status, "Discovering", "discovery", None)
        try:
            self.discovery.run(max_queries=None)
            self.call_from_thread(self.notify, "✓ Discovery complete", severity="information")
        except Exception as e:
            self.call_from_thread(self.notify, f"Discovery failed: {e}", severity="error")
        finally:
            self.call_from_thread(self.update_status, "Idle")

    @work(exclusive=True, thread=True)
    def action_run_audit(self) -> None:
        self.call_from_thread(self.update_status, "Auditing", "audit", None)
        try:
            self.outreach.audit_leads(
                limit=20,
                progress_callback=self._make_progress_callback("Auditing"),
            )
            self.call_from_thread(self.notify, "✓ Audit complete", severity="information")
        except Exception as e:
            self.call_from_thread(self.notify, f"Audit failed: {e}", severity="error")
        finally:
            self.call_from_thread(self.update_status, "Idle")

    @work(exclusive=True, thread=True)
    def action_generate_emails(self) -> None:
        self.call_from_thread(self.update_status, "Generating", "generate", None)
        try:
            self.outreach.generate_emails(
                limit=20,
                progress_callback=self._make_progress_callback("Generating"),
            )
            self.call_from_thread(self.notify, "✓ Generation complete", severity="information")
        except Exception as e:
            self.call_from_thread(self.notify, f"Generation failed: {e}", severity="error")
        finally:
            self.call_from_thread(self.update_status, "Idle")

    def action_review_emails(self) -> None:
        self.push_screen(ReviewScreen())

    def action_database_browser(self) -> None:
        self.push_screen(DatabaseBrowserScreen())

    def action_query_performance(self) -> None:
        self.push_screen(QueryPerformanceScreen())

    def action_show_logs(self) -> None:
        self.push_screen(LogsScreen())

    def get_system_commands(self, screen: Screen) -> Iterable[SystemCommand]:
        yield from super().get_system_commands(screen)
        yield SystemCommand("Run Discovery", "Execute discovery pipeline", self.action_run_discovery)
        yield SystemCommand("Run Audit", "Audit leads for quality", self.action_run_audit)
        yield SystemCommand("Generate Emails", "Generate outreach emails", self.action_generate_emails)
        yield SystemCommand("Review Emails", "Review generated emails", self.action_review_emails)
        yield SystemCommand("Expand Markets", "Discover new markets", self.action_expand_markets)
        yield SystemCommand("Query Performance", "View performance stats", self.action_query_performance)
        yield SystemCommand("Database Browser", "Browse all data", self.action_database_browser)
        yield SystemCommand("Refresh Dashboard", "Refresh stats", self.action_refresh)


if __name__ == "__main__":
    app = WebContractorTUI()
    app.run()
