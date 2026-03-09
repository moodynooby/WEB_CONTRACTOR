"""Market Review Screen - Refactored"""

import json
from typing import Dict
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal
from textual.screen import Screen
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Label,
    Static,
)

from core.db_repository import get_all_buckets, save_config, save_bucket, get_config


class MarketReviewScreen(Screen):
    """Screen for reviewing market expansion suggestions."""
    
    BINDINGS = [
        Binding("escape", "dismiss", "Done"),
        Binding("a", "approve_selected", "Approve"),
        Binding("r", "reject_selected", "Reject"),
    ]
    
    def __init__(self, suggestions: list):
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
        self._setup_table()
        self._refresh_table()
    
    def _setup_table(self) -> None:
        """Setup market suggestions table."""
        table = self.query_one("#market-table", DataTable)
        table.add_columns("Type", "Name", "Details")
        table.cursor_type = "row"
    
    def _refresh_table(self) -> None:
        """Refresh table with current suggestions."""
        table = self.query_one("#market-table", DataTable)
        table.clear()
        
        for i, suggestion in enumerate(self.suggestions):
            stype = "New Bucket" if "new_categories" not in suggestion else "Expansion"
            name = suggestion.get("name") or suggestion.get("bucket_name") or "Expansion"
            details = str(suggestion.get("categories") or suggestion.get("new_categories", []))
            table.add_row(stype, name, details, key=str(i))
    
    def _get_selected_suggestion(self) -> Dict:
        """Get currently selected suggestion."""
        table = self.query_one("#market-table", DataTable)
        if table.cursor_row is not None and table.cursor_row < len(self.suggestions):
            return self.suggestions[table.cursor_row]
        return {}
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "done-market":
            self.dismiss()
        elif event.button.id == "approve-market":
            self.action_approve_selected()
        elif event.button.id == "reject-market":
            self.action_reject_selected()
    
    def action_approve_selected(self) -> None:
        """Approve and apply selected suggestion."""
        suggestion = self._get_selected_suggestion()
        if not suggestion:
            self.notify("No suggestion selected", severity="warning")
            return
        
        if self._apply_suggestion(suggestion):
            idx = self.suggestions.index(suggestion)
            self.suggestions.pop(idx)
            self._refresh_table()
            self.notify("✓ Suggestion applied", severity="information")
    
    def action_reject_selected(self) -> None:
        """Reject selected suggestion."""
        suggestion = self._get_selected_suggestion()
        if not suggestion:
            self.notify("No suggestion selected", severity="warning")
            return
        
        idx = self.suggestions.index(suggestion)
        self.suggestions.pop(idx)
        self._refresh_table()
        self.notify("✗ Suggestion rejected", severity="error")
    
    def _apply_suggestion(self, suggestion: Dict) -> bool:
        """Apply a market suggestion. Returns True on success."""
        try:
            if "new_categories" in suggestion:
                bucket_name = suggestion.get("bucket_name")
                buckets = get_all_buckets()
                bucket = next((b for b in buckets if b["name"] == bucket_name), None)
                
                if bucket:
                    new_cats = list(set(bucket.get("categories", []) + suggestion.get("new_categories", [])))
                    new_pats = list(set(bucket.get("search_patterns", []) + suggestion.get("new_patterns", [])))
                    bucket["categories"] = new_cats
                    bucket["search_patterns"] = new_pats
                    
                    geo_focus = get_config("geographic_focus") or {}
                    if "expanded" not in geo_focus:
                        geo_focus["expanded"] = {"cities": []}
                    geo_focus["expanded"]["cities"] = list(
                        set(geo_focus["expanded"].get("cities", []) + suggestion.get("new_cities", []))
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
                    return True
            else:
                suggestion["geographic_segments"] = ["tier_1_metros"]
                suggestion["conversion_probability"] = 0.5
                suggestion["monthly_target"] = 100
                save_bucket(suggestion)
                return True
        except Exception:
            pass
        return False
