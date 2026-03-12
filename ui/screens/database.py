"""Database Browser Screen - Refactored"""

from typing import Optional
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import DataTable, Header, Footer, Select, Static

from core.db_repository import get_all_buckets
from core.db_models import Lead, EmailCampaign, QueryPerformance


def safe_truncate(value: Optional[str], max_length: int) -> str:
    """Safely truncate a string value, handling None gracefully."""
    if value is None:
        return "N/A"
    return str(value)[:max_length]


class DatabaseScreen(Screen):
    """Screen for browsing database tables."""

    BINDINGS = [
        Binding("escape", "dismiss", "Back"),
        Binding("r", "refresh", "Refresh"),
        Binding("t", "change_table", "Table"),
    ]

    TABLE_TYPES = [
        ("buckets", "🪣 Buckets"),
        ("leads", "🎯 Leads"),
        ("emails", "📧 Emails"),
        ("queries", "⚡ Queries"),
    ]

    COLUMNS_MAP = {
        "buckets": ("ID", "Name", "Priority", "Queries", "Results", "Limit", "Count"),
        "leads": ("ID", "Business", "Category", "Location", "Email", "Status", "Score"),
        "emails": ("ID", "Business", "Subject", "Status", "Sent At"),
        "queries": ("ID", "Bucket", "Query", "City", "Active", "Exec", "Success %"),
    }

    def __init__(self):
        super().__init__()
        self.current_table = "leads"
        self.filter_status = "all"

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="db-browser-container"):
            with Horizontal(id="db-controls"):
                yield Select(
                    [(name, key) for key, name in self.TABLE_TYPES],
                    value=self.current_table,
                    allow_blank=False,
                    id="table-selector",
                )
                yield Select(
                    [
                        ("All", "all"),
                        ("Pending", "pending"),
                        ("Qualified", "qualified"),
                        ("Sent", "sent"),
                    ],
                    value="all",
                    allow_blank=False,
                    id="filter-selector",
                )
                yield Static(
                    f"Table: {self._get_table_display_name()}", id="table-info"
                )

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

    def _setup_table(self) -> None:
        """Setup DataTable columns based on current table type."""
        table = self.query_one("#data-table", DataTable)
        table.clear()
        columns = self.COLUMNS_MAP.get(self.current_table, ("ID", "Data"))
        table.add_columns(*columns)
        table.cursor_type = "row"

    def _refresh_data(self) -> None:
        """Refresh data based on current table and filter."""
        table = self.query_one("#data-table", DataTable)
        table.clear()

        loaders = {
            "buckets": self._load_buckets,
            "leads": self._load_leads,
            "emails": self._load_emails,
            "queries": self._load_queries,
        }
        loader = loaders.get(self.current_table)
        if loader:
            loader()

        count = len(table.rows)
        self.query_one("#table-status", Static).update(
            f"[dim]Showing {count} items | [cyan]↑/↓[/cyan] navigate | [cyan]Enter[/cyan] view | [cyan]esc[/cyan] back[/dim]"
        )

    def _load_buckets(self) -> None:
        table = self.query_one("#data-table", DataTable)
        for bucket in get_all_buckets():
            table.add_row(
                str(bucket.get("id", "N/A")),
                bucket.get("name", "Unknown"),
                str(bucket.get("priority", 1)),
                str(bucket.get("max_queries", 5)),
                str(bucket.get("max_results", 2)),
                str(bucket.get("daily_email_limit", 500)),
                str(bucket.get("daily_email_count", 0)),
            )

    def _load_leads(self) -> None:
        table = self.query_one("#data-table", DataTable)
        query = Lead.select().order_by(Lead.created_at.desc()).limit(100)
        if self.filter_status != "all":
            query = query.where(Lead.status == self.filter_status)

        for lead in query:
            lead_dict = lead.to_dict()
            status = lead_dict.get("status", "pending")
            status_style = (
                "green"
                if status == "qualified"
                else "yellow"
                if status == "pending_audit"
                else "default"
            )
            table.add_row(
                str(lead_dict.get("id", "N/A")),
                safe_truncate(lead_dict.get("business_name"), 25),
                safe_truncate(lead_dict.get("category"), 15),
                safe_truncate(lead_dict.get("location"), 15),
                safe_truncate(lead_dict.get("email"), 20),
                f"[{status_style}]{status}[/{status_style}]",
                f"{lead_dict.get('quality_score', 0):.2f}",
            )

    def _load_emails(self) -> None:
        table = self.query_one("#data-table", DataTable)
        query = (
            EmailCampaign.select()
            .order_by(
                EmailCampaign.sent_at.desc()
                if EmailCampaign.sent_at
                else EmailCampaign.created_at.desc()
            )
            .limit(100)
        )
        if self.filter_status != "all":
            query = query.where(EmailCampaign.status == self.filter_status)

        for email in query:
            lead = email.lead
            business_name = lead.business_name if lead else "N/A"
            sent_at = email.sent_at.strftime("%Y-%m-%d") if email.sent_at else "N/A"
            status_style = (
                "green"
                if email.status == "sent"
                else "yellow"
                if email.status == "pending"
                else "red"
            )
            table.add_row(
                str(email.id),
                safe_truncate(business_name, 25),
                safe_truncate(email.subject, 30),
                f"[{status_style}]{email.status}[/{status_style}]",
                sent_at,
            )

    def _load_queries(self) -> None:
        table = self.query_one("#data-table", DataTable)
        for qp in (
            QueryPerformance.select()
            .order_by(QueryPerformance.total_executions.desc())
            .limit(100)
        ):
            qp_dict = qp.to_dict()
            success_rate = 0
            if qp.total_executions > 0:
                success_rate = (qp.total_leads_found / qp.total_executions) * 100
            active_str = "[green]✓[/green]" if qp.is_active else "[red]✗[/red]"
            table.add_row(
                str(qp_dict.get("id", "N/A")),
                safe_truncate(qp_dict.get("bucket"), 12),
                safe_truncate(qp_dict.get("query_pattern"), 20),
                safe_truncate(qp_dict.get("city"), 12),
                active_str,
                str(qp_dict.get("total_executions", 0)),
                f"[green]{success_rate:.1f}%[/green]"
                if success_rate > 50
                else f"[red]{success_rate:.1f}%[/red]",
            )

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "table-selector":
            self.current_table = str(event.value)
            self._setup_table()
            self._refresh_data()
        elif event.select.id == "filter-selector":
            self.filter_status = str(event.value)
            self._refresh_data()

    def action_refresh(self) -> None:
        self._refresh_data()
        self.notify("Data refreshed")

    def action_change_table(self) -> None:
        self.query_one("#table-selector", Select).focus()
