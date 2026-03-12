"""Review Screen and Refine Modal - Refactored"""

from typing import Dict, Optional
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen, Screen
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    Static,
)


from core.db_repository import (
    get_emails_for_review,
    update_email_content,
    delete_email,
    mark_email_sent,
)


class ReviewScreen(Screen):
    """Screen for reviewing and managing generated emails."""

    BINDINGS = [
        Binding("escape", "dismiss", "Back"),
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
        self.selected_email: Optional[Dict] = None
        self.emails: list = []
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
                yield Button(
                    "[green]✓[/green] Approve & Send",
                    variant="success",
                    id="approve-btn",
                )
                yield Button(
                    "[green]✓[/green] Generate",
                    variant="success",
                    id="generate-btn",
                )

                yield Button("[cyan]✎[/cyan] Edit", variant="primary", id="edit-btn")
                yield Button(
                    "[yellow]✦[/yellow] AI Rewrite", variant="warning", id="rewrite-btn"
                )
                yield Button("[red]✗[/red] Delete", variant="error", id="delete-btn")
        yield Footer()

    def on_mount(self) -> None:
        self._setup_table()
        self.refresh_emails()

    def _setup_table(self) -> None:
        """Setup email table."""
        table = self.query_one("#email-table", DataTable)
        table.add_columns("Business", "Subject")
        table.cursor_type = "row"

    def refresh_emails(self) -> None:
        """Refresh email list and detail view."""
        table = self.query_one("#email-table", DataTable)
        table.clear()
        self.emails = get_emails_for_review()

        for i, email in enumerate(self.emails):
            table.add_row(
                email["business_name"], email["subject"], key=str(email["id"])
            )

        if not self.emails:
            self.query_one("#email-details", Static).update(
                "[dim]No emails pending review.[/dim]\n\n"
                "[cyan]Run 'Generate Emails' from dashboard to create outreach emails.[/cyan]"
            )
            self.query_one("#email-counter", Static).update("")
            self.selected_email = None
            return

        if self.selected_email:
            new_data = next(
                (e for e in self.emails if e["id"] == self.selected_email["id"]), None
            )
            self.selected_email = new_data if new_data else self.emails[0]
        else:
            self.selected_email = self.emails[0] if self.emails else None

        self._update_counter()
        for idx, email in enumerate(self.emails):
            if email["id"] == self.selected_email["id"]:
                table.move_cursor(row=idx)
                self.current_index = idx
                break

        self.update_detail_view()

    def _update_counter(self) -> None:
        """Update email counter display."""
        total = len(self.emails)
        current = self.current_index + 1 if self.emails else 0
        self.query_one("#email-counter", Static).update(
            f"[bold]Email {current} of {total}[/bold]"
        )

    def update_detail_view(self) -> None:
        """Update email detail panel."""
        if not self.selected_email:
            self.query_one("#email-details", Static).update(
                "[dim]No email selected.[/dim]"
            )
            return

        email = self.selected_email
        content = f"""[bold][cyan]To:[/cyan][/bold] {email.get("email", "N/A")}
[bold][cyan]Subject:[/cyan][/bold] {email["subject"]}
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

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle email selection from table."""
        if event.row_key.value is None:
            return
        try:
            email_id = int(event.row_key.value)
            self.selected_email = next(
                (e for e in self.emails if e["id"] == email_id), None
            )
            if self.selected_email:
                for idx, email in enumerate(self.emails):
                    if email["id"] == email_id:
                        self.current_index = idx
                        break
                self.update_detail_view()
                self._update_counter()
        except (ValueError, TypeError):
            self.notify("Invalid selection", severity="error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button clicks."""
        button_id = event.button.id

        if button_id == "approve-btn":
            self.action_approve_selected()
        elif button_id == "generate-btn":
            self.action_generate_emails()
        elif button_id == "edit-btn":
            self.action_edit_selected()
        elif button_id == "rewrite-btn":
            self.action_refine_email()
        elif button_id == "delete-btn":
            self.action_delete_selected()

    def action_next_email(self) -> None:
        """Navigate to next email."""
        if self.emails and self.current_index < len(self.emails) - 1:
            self.current_index += 1
            self.selected_email = self.emails[self.current_index]
            table = self.query_one("#email-table", DataTable)
            table.move_cursor(row=self.current_index)
            self.update_detail_view()
            self._update_counter()

    def action_prev_email(self) -> None:
        """Navigate to previous email."""
        if self.emails and self.current_index > 0:
            self.current_index -= 1
            self.selected_email = self.emails[self.current_index]
            table = self.query_one("#email-table", DataTable)
            table.move_cursor(row=self.current_index)
            self.update_detail_view()
            self._update_counter()

    def action_approve_selected(self) -> None:
        """Approve and send selected email."""
        if not self.selected_email:
            return

        email_id = self.selected_email["id"]
        to_email = self.selected_email.get("email")
        subject = self.selected_email["subject"]
        body = self.selected_email["body"]

        if not to_email:
            self.notify("No email address!", severity="error")
            return

        self.notify(f"Sending to {self.selected_email['business_name']}...")

        self._send_email_and_callback(email_id, to_email, subject, body)

    def _send_email_and_callback(
        self, email_id: int, to_email: str, subject: str, body: str
    ) -> None:
        """Send email in background and update UI."""

        def send_task():
            success = self.app.app_core.send_email(to_email, subject, body)

            self.call_after_refresh(lambda: self._on_email_sent(email_id, success))

        self.run_worker(send_task, exclusive=True, thread=True)

    def _on_email_sent(self, email_id: int, success: bool) -> None:
        """Callback after email is sent."""
        mark_email_sent(email_id, True if success else False)
        if success:
            self.notify("✓ Email sent!", severity="information")
        else:
            self.notify("✗ Send failed", severity="error")
        self.refresh_emails()

    def action_delete_selected(self) -> None:
        """Delete selected email."""
        if self.selected_email:
            delete_email(self.selected_email["id"])
            self.notify(
                f"Deleted: {self.selected_email['business_name']}", severity="error"
            )
            self.refresh_emails()

    def action_edit_selected(self) -> None:
        """Edit selected email using external editor."""
        if not self.selected_email:
            return

        import click

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

    def action_refine_email(self) -> None:
        """AI rewrite of selected email."""
        if not self.selected_email:
            return

        self._show_refine_modal()

    def _show_refine_modal(self) -> None:
        """Show refine modal and handle result."""

        def on_modal_close(result):
            if result:
                self._refine_email(result)

        self.app.push_screen(RefineEmailModal(), on_modal_close)

    def _refine_email(self, instructions: str) -> None:
        """Refine email using LLM in background."""
        self.notify("AI refining...")

        def refine_task():
            result = self.app.app_core.email_generator.refine(
                self.selected_email["subject"],
                self.selected_email["body"],
                instructions,
            )

            self.call_after_refresh(lambda: self._on_email_refined(result))

        self.run_worker(refine_task, exclusive=True, thread=True)

    def _on_email_refined(self, result: dict) -> None:
        """Callback after email is refined."""
        if result:
            update_email_content(
                self.selected_email["id"], result["subject"], result["body"]
            )
            self.notify("✓ AI rewrite complete!")
            self.refresh_emails()

    def action_generate_emails(self) -> None:
        """Generate emails."""
        self.run_worker(self.app.app_core.generate_emails, exclusive=True, thread=True)


class RefineEmailModal(ModalScreen):
    """Modal for entering AI refinement instructions."""

    MAX_INSTRUCTIONS_LENGTH = 500

    BINDINGS = [
        Binding("escape", "dismiss_cancel", "Cancel"),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="refine-container"):
            yield Label("[bold]AI Refinement Instructions[/bold]")
            yield Label(
                "[dim]e.g. 'Make it shorter', 'Mention portfolio', 'Be more formal'[/dim]"
            )
            yield Input(
                placeholder="Enter instructions...",
                id="refine-input",
                max_length=self.MAX_INSTRUCTIONS_LENGTH,
            )
            with Horizontal(id="refine-buttons"):
                yield Button("Refine", variant="success", id="refine-btn")
                yield Button("Cancel", variant="error", id="cancel-btn")

    def on_mount(self) -> None:
        self.query_one("#refine-input", Input).focus()

    def _validate_and_dismiss(self, instructions: str) -> None:
        """Validate instructions and dismiss modal."""
        if not instructions or not instructions.strip():
            self.notify("Please enter instructions", severity="warning")
            return

        if len(instructions) > self.MAX_INSTRUCTIONS_LENGTH:
            self.notify(f"Max {self.MAX_INSTRUCTIONS_LENGTH} chars", severity="error")
            return

        self.dismiss(instructions.strip())

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "refine-btn":
            instructions = self.query_one("#refine-input", Input).value
            self._validate_and_dismiss(instructions)
        else:
            self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._validate_and_dismiss(event.value)

    def dismiss_cancel(self) -> None:
        self.dismiss(None)
