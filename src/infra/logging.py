"""Standard Python Logging for Web Contractor.

Centralized logging with colored console output and GUI streaming.
All logs go to stderr and GUI consumers via LogStreamer.
"""

import logging
import queue
import sys
import threading
from typing import Optional


COLORS = {
    "DEBUG": "\033[36m",
    "INFO": "\033[96m",
    "WARNING": "\033[93m",
    "ERROR": "\033[91m",
    "CRITICAL": "\033[95m",
    "RESET": "\033[0m",
}

SYMBOLS = {
    "DEBUG": "🔍",
    "INFO": "ℹ️",
    "WARNING": "⚠️",
    "ERROR": "❌",
    "CRITICAL": "🚨",
}

_FORMAT = "[%(asctime)s] %(levelname)s (%(name)s) - %(message)s"
_DATEFMT = "%H:%M:%S"


class ColoredFormatter(logging.Formatter):
    """Formatter with colors and symbols for console output."""

    def format(self, record: logging.LogRecord) -> str:
        color = COLORS.get(record.levelname, COLORS["RESET"])
        symbol = SYMBOLS.get(record.levelname, "")
        reset = COLORS["RESET"]
        record.msg = f"{color}{symbol} {record.msg}{reset}"
        return super().format(record)


class LogStreamer:
    """Thread-safe log message distributor for GUI consumers."""

    def __init__(self):
        self._subscribers: list[queue.Queue] = []
        self._lock = threading.Lock()

    def subscribe(self) -> queue.Queue:
        """Subscribe to log messages."""
        q: queue.Queue = queue.Queue()
        with self._lock:
            self._subscribers.append(q)
        return q

    def publish(self, message: str, level: str = "INFO") -> None:
        """Publish a log message to all subscribers."""
        with self._lock:
            subscribers = list(self._subscribers)
        for q in subscribers:
            try:
                q.put_nowait((message, level))
            except queue.Full:
                pass


_global_log_streamer: Optional[LogStreamer] = None
_streamer_lock = threading.Lock()


def get_log_streamer() -> LogStreamer:
    """Get the global log streamer instance (creates if needed)."""
    global _global_log_streamer
    with _streamer_lock:
        if _global_log_streamer is None:
            _global_log_streamer = LogStreamer()
        return _global_log_streamer


class GUIHandler(logging.Handler):
    """Handler that pushes log records to the GUI log streamer."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            get_log_streamer().publish(msg, record.levelname)
        except Exception:
            self.handleError(record)


_console_handler: Optional[logging.Handler] = None
_gui_handler: Optional[logging.Handler] = None
_handler_lock = threading.Lock()


def _get_handlers() -> tuple[logging.Handler, logging.Handler]:
    """Get or create the singleton console and GUI handlers."""
    global _console_handler, _gui_handler
    with _handler_lock:
        if _console_handler is None:
            formatter = ColoredFormatter(_FORMAT, datefmt=_DATEFMT)

            _console_handler = logging.StreamHandler(sys.stderr)
            _console_handler.setFormatter(formatter)

            _gui_handler = GUIHandler()
            _gui_handler.setFormatter(formatter)

        assert _console_handler is not None
        assert _gui_handler is not None
        return _console_handler, _gui_handler


def get_logger(name: str, level: str = "INFO") -> logging.Logger:
    """Get a configured logger for a module.

    Args:
        name: Module name (typically __name__)
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)

    if not logger.handlers:
        log_level = getattr(logging, level.upper(), logging.INFO)
        logger.setLevel(log_level)

        console_handler, gui_handler = _get_handlers()
        logger.addHandler(console_handler)
        logger.addHandler(gui_handler)
        logger.propagate = False

    return logger
