"""Base Screen Classes for Web Contractor TUI

Common base classes to reduce duplication across screens.
"""

from typing import Any, Callable, List, Optional, Tuple
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import DataTable, Static, Button



class BaseScreen(Screen):
    """Base class for all screens with common functionality."""
    
    BINDINGS = [
        Binding("escape", "dismiss", "Back", show=True),
    ]
    
    def dismiss(self, result: Any = None) -> None:
        """Dismiss screen and return to parent."""
        self.app.pop_screen()


class DataTableScreen(BaseScreen):
    """
    Base class for screens displaying a single DataTable.
    
    Provides:
    - Standard table setup
    - Data loading pattern
    - Status message updates
    - Refresh action
    """
    
    BINDINGS = [
        Binding("escape", "dismiss", "Back"),
        Binding("r", "refresh", "Refresh"),
    ]
    
    COLUMNS: Tuple[str, ...] = ("ID", "Data")
    TABLE_ID: str = "data-table"
    STATUS_ID: str = "table-status"
    
    def __init__(self):
        super().__init__()
        self._data_loaded = False
    
    def compose(self) -> ComposeResult:
        """Override in subclass to compose screen layout."""
        raise NotImplementedError
    
    def setup_table(self, columns: Optional[Tuple[str, ...]] = None) -> None:
        """
        Setup DataTable with columns.
        
        Args:
            columns: Column names, or use class default COLUMNS
        """
        table = self.query_one(f"#{self.TABLE_ID}", DataTable)
        table.clear()
        table.add_columns(*(columns or self.COLUMNS))
        table.cursor_type = "row"
    
    def load_data(self, get_data: Callable[[], List[Any]]) -> int:
        """
        Load data into table using provided getter function.
        
        Args:
            get_data: Function that returns list of row data tuples
            
        Returns:
            Number of rows loaded
        """
        table = self.query_one(f"#{self.TABLE_ID}", DataTable)
        table.clear()
        
        rows = get_data()
        for row_data in rows:
            if isinstance(row_data, (list, tuple)):
                table.add_row(*row_data)
            else:
                table.add_row(row_data)
        
        self.update_status(len(rows))
        self._data_loaded = True
        return len(rows)
    
    def update_status(self, count: Optional[int] = None, message: str = "") -> None:
        """
        Update status message.
        
        Args:
            count: Optional item count to display
            message: Custom message (uses default if not provided)
        """
        status_widget = self.query_one(f"#{self.STATUS_ID}", Static)
        
        if not message:
            nav_hint = " | [cyan]↑/↓[/cyan] navigate | [cyan]Enter[/cyan] view | [cyan]esc[/cyan] back"
            count_str = f"Showing {count} items" if count is not None else "No data"
            message = f"[dim]{count_str}{nav_hint}[/dim]"
        
        status_widget.update(message)
    
    def action_refresh(self) -> None:
        """Refresh table data. Override _load_data() in subclass."""
        self._load_data()
        self.notify("Data refreshed")
    
    def _load_data(self) -> None:
        """Override in subclass to implement data loading logic."""
        raise NotImplementedError


class DualTableScreen(BaseScreen):
    """
    Base class for screens with two side-by-side DataTables.
    
    Provides:
    - Standard dual table setup
    - Synchronized data loading
    - Common refresh action
    """
    
    BINDINGS = [
        Binding("escape", "dismiss", "Back"),
        Binding("r", "refresh", "Refresh"),
    ]
    
    LEFT_COLUMNS: Tuple[str, ...] = ("ID", "Data")
    RIGHT_COLUMNS: Tuple[str, ...] = ("ID", "Data")
    LEFT_TABLE_ID: str = "left-table"
    RIGHT_TABLE_ID: str = "right-table"
    
    def compose(self) -> ComposeResult:
        """Override in subclass to compose screen layout."""
        raise NotImplementedError
    
    def setup_tables(
        self,
        left_columns: Optional[Tuple[str, ...]] = None,
        right_columns: Optional[Tuple[str, ...]] = None,
    ) -> None:
        """
        Setup both DataTables with columns.
        
        Args:
            left_columns: Left table column names
            right_columns: Right table column names
        """
        left_table = self.query_one(f"#{self.LEFT_TABLE_ID}", DataTable)
        left_table.clear()
        left_table.add_columns(*(left_columns or self.LEFT_COLUMNS))
        left_table.cursor_type = "row"
        
        right_table = self.query_one(f"#{self.RIGHT_TABLE_ID}", DataTable)
        right_table.clear()
        right_table.add_columns(*(right_columns or self.RIGHT_COLUMNS))
        right_table.cursor_type = "row"
    
    def load_tables(
        self,
        get_left_data: Callable[[], List[Any]],
        get_right_data: Callable[[], List[Any]],
    ) -> Tuple[int, int]:
        """
        Load data into both tables.
        
        Args:
            get_left_data: Function returning left table row data
            get_right_data: Function returning right table row data
            
        Returns:
            Tuple of (left_count, right_count)
        """
        left_table = self.query_one(f"#{self.LEFT_TABLE_ID}", DataTable)
        left_table.clear()
        left_rows = get_left_data()
        for row_data in left_rows:
            if isinstance(row_data, (list, tuple)):
                left_table.add_row(*row_data)
            else:
                left_table.add_row(row_data)
        
        right_table = self.query_one(f"#{self.RIGHT_TABLE_ID}", DataTable)
        right_table.clear()
        right_rows = get_right_data()
        for row_data in right_rows:
            if isinstance(row_data, (list, tuple)):
                right_table.add_row(*row_data)
            else:
                right_table.add_row(row_data)
        
        return (len(left_rows), len(right_rows))
    
    def action_refresh(self) -> None:
        """Refresh both tables. Override _load_tables() in subclass."""
        self._load_tables()
        self.notify("Data refreshed")
    
    def _load_tables(self) -> None:
        """Override in subclass to implement data loading logic."""
        raise NotImplementedError


class ModalScreenBase(Screen):
    """
    Base class for modal dialogs with standard button handling.
    
    Provides:
    - Standard button container
    - Escape to dismiss
    - Common button event handling
    """
    
    BINDINGS = [
        Binding("escape", "dismiss_cancel", "Cancel"),
    ]
    
    def compose(self) -> ComposeResult:
        """Override in subclass to compose modal content."""
        raise NotImplementedError
    
    def dismiss_cancel(self) -> None:
        """Dismiss with None/cancel result."""
        self.dismiss(None)
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        """
        Handle button press. Override in subclass.
        
        Default behavior: dismiss with button ID.
        """
        self.dismiss(event.button.id)
