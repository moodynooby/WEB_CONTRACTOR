"""Status Bar Widget.

Displays database connection status and quick stats.
"""

from PyQt6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel, QFrame
from PyQt6.QtGui import QFont


class StatusBar(QWidget):
    """Database status indicator and quick stats display."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Build the status bar layout."""
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        db_layout = QHBoxLayout()
        db_layout.setSpacing(8)

        self.db_indicator = QLabel("●")
        self.db_indicator.setStyleSheet("color: gray; font-size: 16px;")
        self.db_indicator.setFixedWidth(20)
        db_layout.addWidget(self.db_indicator)

        self.db_status_label = QLabel("Checking...")
        self.db_status_label.setStyleSheet("color: gray;")
        db_layout.addWidget(self.db_status_label)

        db_layout.addStretch()
        layout.addLayout(db_layout)

        stats_layout = QHBoxLayout()
        stats_layout.setSpacing(15)

        self.stat_labels: dict[str, QLabel] = {}
        for label_text in [
            "Buckets",
            "Pending Audits",
            "Qualified Leads",
            "Emails for Review",
        ]:
            stat_widget = QWidget()
            stat_layout = QHBoxLayout(stat_widget)
            stat_layout.setContentsMargins(0, 0, 0, 0)
            stat_layout.setSpacing(5)

            label = QLabel(f"{label_text}:")
            label.setStyleSheet("color: #aaa;")
            stat_layout.addWidget(label)

            value_label = QLabel("-")
            value_label.setStyleSheet("color: #fcfcfc; font-weight: bold;")
            value_label.setFont(QFont("", 11))
            stat_layout.addWidget(value_label)

            self.stat_labels[label_text] = value_label
            stats_layout.addWidget(stat_widget)

        stats_layout.addStretch()
        layout.addLayout(stats_layout)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(line)

    def set_db_status(self, connected: bool, database_name: str = "") -> None:
        """Update database connection status display.

        Args:
            connected: Whether the database is connected.
            database_name: Name of the connected database.
        """
        if connected:
            self.db_indicator.setStyleSheet("color: #4caf50; font-size: 16px;")
            db_name = f" ({database_name})" if database_name else ""
            self.db_status_label.setText(f"Connected{db_name}")
            self.db_status_label.setStyleSheet("color: #4caf50;")
        else:
            self.db_indicator.setStyleSheet("color: #f44336; font-size: 16px;")
            self.db_status_label.setText("Disconnected")
            self.db_status_label.setStyleSheet("color: #f44336;")

    def update_stats(self, stats: dict[str, int]) -> None:
        """Update quick stats from database.

        Args:
            stats: Dictionary mapping stat names to their values.
        """
        for stat_name, value in stats.items():
            if stat_name in self.stat_labels:
                self.stat_labels[stat_name].setText(str(value))
