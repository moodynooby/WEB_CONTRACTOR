"""Reusable UI Components for Web Contractor TUI

Common widgets and components to reduce duplication across screens.
"""

from typing import List, Optional, Tuple
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import (
    Button,
    DataTable,
    Label,
    Select,
    Static,
)



class StatusMessage(Static):
    """Reusable status message widget with standard formatting."""
    
    DEFAULT_CSS = """
    StatusMessage {
        height: 1;
        text-align: center;
        color: $text-muted;
        padding: 0 2;
    }
    """
    
    def __init__(self, message: str = "", id: Optional[str] = None):
        super().__init__(message, id=id)
    
    def update_status(self, message: str, count: Optional[int] = None) -> None:
        """Update status message with optional count."""
        if count is not None:
            self.update(f"[dim]{message} ({count} items)[/dim]")
        else:
            self.update(f"[dim]{message}[/dim]")


class ActionButtonPanel(Horizontal):
    """Standardized action button panel with consistent styling."""
    
    DEFAULT_CSS = """
    ActionButtonPanel {
        height: 3;
        align: center middle;
        margin-top: 1;
    }
    
    ActionButtonPanel Button {
        margin: 0 1;
        min-width: 12;
    }
    """
    
    def __init__(
        self,
        buttons: List[Tuple[str, str, str]],  
        id: Optional[str] = None,
    ):
        super().__init__(id=id)
        self.button_configs = buttons
    
    def compose(self) -> ComposeResult:
        for label, variant, btn_id in self.button_configs:
            yield Button(label, variant=variant, id=btn_id)


class DataTableFooter(Static):
    """Standard footer for DataTable screens with navigation hints."""
    
    DEFAULT_CSS = """
    DataTableFooter {
        height: 1;
        text-align: center;
        color: $text-muted;
    }
    """
    
    def __init__(self, show_navigation: bool = True, id: Optional[str] = None):
        super().__init__(id=id)
        self.show_navigation = show_navigation
    
    def update_count(self, count: int) -> None:
        """Update item count display."""
        nav_hint = " | ↑/↓ navigate | Enter view | esc back" if self.show_navigation else ""
        self.update(f"[dim]Showing {count} items{nav_hint}[/dim]")



class TableFilterPanel(Horizontal):
    """Standard filter panel for DataTable screens."""
    
    DEFAULT_CSS = """
    TableFilterPanel {
        height: 3;
        margin-bottom: 1;
    }
    
    TableFilterPanel Select {
        width: 30%;
    }
    
    TableFilterPanel Static {
        width: 45%;
        content-align: right middle;
    }
    """
    
    def __init__(
        self,
        table_options: List[Tuple[str, str]],
        filter_options: Optional[List[Tuple[str, str]]] = None,
        id: Optional[str] = None,
    ):
        """
        Args:
            table_options: List of (display_name, key) for table selector
            filter_options: Optional list of (display_name, key) for filter selector
            id: Widget ID
        """
        super().__init__(id=id)
        self.table_options = table_options
        self.filter_options = filter_options or []
    
    def compose(self) -> ComposeResult:
        if self.table_options:
            yield Select(
                [(name, key) for key, name in self.table_options],
                value=self.table_options[0][1] if self.table_options else None,
                allow_blank=False,
                id="table-selector"
            )
        
        if self.filter_options:
            yield Select(
                self.filter_options,
                value=self.filter_options[0][1] if self.filter_options else None,
                allow_blank=False,
                id="filter-selector"
            )
        
        yield Static("", id="table-info")



class StatsRow(Horizontal):
    """Row of statistics displays."""
    
    DEFAULT_CSS = """
    StatsRow {
        height: auto;
        margin-bottom: 1;
    }
    
    StatsRow Static {
        padding: 1;
        width: 50%;
        border: solid $primary;
    }
    """
    
    def __init__(self, left_id: str = "left-stats", right_id: str = "right-stats", id: Optional[str] = None):
        super().__init__(id=id)
        self.left_id = left_id
        self.right_id = right_id
    
    def compose(self) -> ComposeResult:
        yield Static("Loading...", id=self.left_id)
        yield Static("Loading...", id=self.right_id)


class DualTablePanel(Horizontal):
    """Panel with two side-by-side DataTables."""
    
    DEFAULT_CSS = """
    DualTablePanel {
        height: 1fr;
    }
    
    DualTablePanel Vertical {
        width: 50%;
        border: solid $primary;
        padding: 1;
    }
    
    DualTablePanel DataTable {
        height: 1fr;
    }
    """
    
    def __init__(
        self,
        left_label: str,
        right_label: str,
        left_id: str = "left-table",
        right_id: str = "right-table",
        id: Optional[str] = None,
    ):
        super().__init__(id=id)
        self.left_label = left_label
        self.right_label = right_label
        self.left_id = left_id
        self.right_id = right_id
    
    def compose(self) -> ComposeResult:
        with Vertical(id=f"{self.left_id}-section"):
            yield Label(f"[green]{self.left_label}[/green]")
            yield DataTable(id=self.left_id)
        
        with Vertical(id=f"{self.right_id}-section"):
            yield Label(f"[red]{self.right_label}[/red]")
            yield DataTable(id=self.right_id)



def create_button_config(
    label: str,
    variant: str = "default",
    icon: Optional[str] = None,
    suffix_id: str = "",
) -> Tuple[str, str, str]:
    """Create standardized button configuration tuple.
    
    Args:
        label: Button text
        variant: Button variant (default, primary, success, warning, error)
        icon: Optional emoji/icon prefix
        suffix_id: Optional suffix for button ID
    
    Returns:
        Tuple of (full_label, variant, button_id)
    """
    full_label = f"{icon} {label}" if icon else label
    button_id = f"{label.lower().replace(' ', '-').replace('/', '-')}"
    if suffix_id:
        button_id = f"{button_id}-{suffix_id}"
    return (full_label, variant, button_id)


def standard_navigation_bindings() -> List[Tuple[str, str, str]]:
    """Return standard navigation key bindings."""
    return [
        ("escape", "app.pop_screen", "Back"),
        ("r", "refresh", "Refresh"),
    ]
