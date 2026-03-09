"""Controllers for Web Contractor TUI

Handles screen navigation.
"""

from typing import Dict
from textual.screen import Screen

from core.app_core import WebContractorApp


class NavigationController:
    """
    Handles screen navigation and system commands.

    Responsibilities:
    - Screen transitions
    - System command registration
    """

    def __init__(self, app, screens: Dict[str, type], app_core: WebContractorApp):
        """
        Args:
            app: Parent TUI app instance
            screens: Dictionary of screen name -> screen class
            app_core: Application core for service access
        """
        self.app = app
        self.screens = screens
        self.app_core = app_core

    def navigate_to(self, screen_name: str) -> None:
        """Navigate to a screen by name."""
        if screen_name in self.screens:
            self.app.push_screen(self.screens[screen_name]())

    def get_system_commands(self, screen: Screen) -> list:
        """Get system commands for command palette."""
        # Get default system commands from parent
        commands = list(self.app.__class__.get_system_commands(self.app, screen))

        # Add our custom commands
        commands.extend([
            ("Run Discovery", "Execute discovery pipeline", self.app.action_run_discovery),
            ("Run Audit", "Audit leads for quality", self.app.action_run_audit),
            ("Generate Emails", "Generate outreach emails", self.app.action_generate_emails),
            ("Review Emails", "Review generated emails", lambda: self.navigate_to("review")),
            ("Database Browser", "Browse all data", lambda: self.navigate_to("database")),
            ("Query Performance", "View performance stats", lambda: self.navigate_to("performance")),
            ("Activity Logs", "View activity logs", lambda: self.navigate_to("logs")),
            ("Refresh Dashboard", "Refresh dashboard stats", self.app.dashboard.refresh_dashboard),
        ])

        return commands
