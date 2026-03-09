"""Logs and Performance Screens - Refactored"""

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Label,
    RichLog,
    Static,
)

from core.db_repository import (
    get_query_performance_stats,
    get_overall_efficiency_metrics,
    get_top_performing_queries,
    get_worst_performing_queries,
)



class QueryPerformanceScreen(Screen):
    """Screen for viewing query performance metrics."""
    
    BINDINGS = [
        Binding("escape", "dismiss", "Back"),
        Binding("r", "refresh", "Refresh"),
    ]
    
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
        self._setup_tables()
        self.refresh_all()
    
    def _setup_tables(self) -> None:
        """Setup both DataTables."""
        columns = ("Bucket", "Query", "City", "Success %", "Exec")
        
        top_table = self.query_one("#top-table", DataTable)
        top_table.add_columns(*columns)
        top_table.cursor_type = "row"
        
        bottom_table = self.query_one("#bottom-table", DataTable)
        bottom_table.add_columns(*columns)
        bottom_table.cursor_type = "row"
    
    def refresh_all(self) -> None:
        """Refresh all displays."""
        self._refresh_stats()
        self._refresh_efficiency()
        self._refresh_tables()
    
    def _refresh_stats(self) -> None:
        """Refresh performance stats display."""
        stats = get_query_performance_stats()
        content = (
            f"[bold]Overview[/bold] | "
            f"Total: [cyan]{stats['total_queries']}[/cyan] | "
            f"Active: [green]{stats['active_queries']}[/green] | "
            f"Stale: [red]{stats['stale_queries']}[/red] | "
            f"Executions: {stats['total_executions']} | "
            f"Leads: {stats['total_leads_found']} | "
            f"Success Rate: [bold green]{stats['average_success_rate']}%[/bold green]"
        )
        self.query_one("#perf-stats", Static).update(content)
    
    def _refresh_efficiency(self) -> None:
        """Refresh efficiency metrics display."""
        metrics = get_overall_efficiency_metrics()
        content = (
            f"[bold]Efficiency[/bold] | "
            f"Leads/Exec: [bold]{metrics['leads_per_execution']}[/bold] | "
            f"Save Rate: [bold green]{metrics['save_rate']}%[/bold green] | "
            f"Qualification: [bold]{metrics['qualification_rate']}%[/bold] | "
            f"Saved: {metrics['total_leads_saved']}/{metrics['total_leads_found']}"
        )
        self.query_one("#efficiency-stats", Static).update(content)
    
    def _refresh_tables(self) -> None:
        """Refresh both data tables."""
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
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "done-btn":
            self.dismiss()
        elif event.button.id == "refresh-btn":
            self.action_refresh()
    
    def action_refresh(self) -> None:
        self.refresh_all()
        self.notify("Statistics refreshed")
