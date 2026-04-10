"""Log Console Widget.

Scrolling text widget for real-time log output.
"""

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QPlainTextEdit, QPushButton, QHBoxLayout
from PyQt6.QtGui import QFont, QTextCursor


class LogConsole(QWidget):
    """Scrolling log console with clear button."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Build log console layout."""
        layout = QVBoxLayout(self)
        layout.setSpacing(5)

        self.log_text = QPlainTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Courier", 10))
        self.log_text.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        layout.addWidget(self.log_text)

        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.clear_btn = QPushButton("Clear Log")
        self.clear_btn.setFixedWidth(100)
        self.clear_btn.clicked.connect(self.clear)
        button_layout.addWidget(self.clear_btn)

        layout.addLayout(button_layout)

    def append_message(self, message: str) -> None:
        """Append a message to the log console.

        Auto-scrolls to the bottom after appending.

        Args:
            message: Log message to display.
        """
        self.log_text.appendPlainText(message)

        cursor = self.log_text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.log_text.setTextCursor(cursor)

    def clear(self) -> None:
        """Clear the log console."""
        self.log_text.clear()
