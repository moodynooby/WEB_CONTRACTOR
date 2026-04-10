"""Standard Python Logging Setup for Web Contractor.

Provides a unified logging configuration across all modules.
No file logging - logs go to console (stderr) only.

Features:
- Colored console output with symbols
- Thread-safe log streaming for GUI consumers
- Multiple subscriber support
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


class ColoredFormatter(logging.Formatter):
    """Custom formatter with colors and symbols for console output."""

    def format(self, record: logging.LogRecord) -> str:
        color = COLORS.get(record.levelname, COLORS["RESET"])
        symbol = SYMBOLS.get(record.levelname, "")
        reset = COLORS["RESET"]

        record.msg = f"{color}{symbol} {record.msg}{reset}"
        return super().format(record)


class LogStreamer:
    """Thread-safe log message distributor for GUI consumers.
    
    Allows multiple subscribers (e.g., Tkinter GUI) to receive log messages
    in a thread-safe manner using queues.
    """
    
    def __init__(self):
        self._subscribers: list[queue.Queue] = []
        self._lock = threading.Lock()
    
    def subscribe(self) -> queue.Queue:
        """Subscribe to log messages.
        
        Returns:
            A thread-safe queue that will receive log messages.
        """
        q: queue.Queue = queue.Queue()
        with self._lock:
            self._subscribers.append(q)
        return q
    
    def unsubscribe(self, q: queue.Queue) -> None:
        """Unsubscribe from log messages.
        
        Args:
            q: The queue to remove from subscribers.
        """
        with self._lock:
            if q in self._subscribers:
                self._subscribers.remove(q)
    
    def publish(self, message: str, level: str = "INFO") -> None:
        """Publish a log message to all subscribers.
        
        Args:
            message: The log message text.
            level: Log level string (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        """
        with self._lock:
            subscribers = list(self._subscribers)
        
        for q in subscribers:
            try:
                q.put_nowait((message, level))
            except queue.Full:
                pass  # Drop message if queue is full
    
    def clear(self) -> None:
        """Remove all subscribers and clear queues."""
        with self._lock:
            for q in self._subscribers:
                while not q.empty():
                    try:
                        q.get_nowait()
                    except queue.Empty:
                        break
            self._subscribers.clear()


# Global log streamer instance for GUI integration
_global_log_streamer: Optional[LogStreamer] = None
_streamer_lock = threading.Lock()


def get_log_streamer() -> LogStreamer:
    """Get the global log streamer instance (creates if needed).
    
    Returns:
        The singleton LogStreamer instance.
    """
    global _global_log_streamer
    with _streamer_lock:
        if _global_log_streamer is None:
            _global_log_streamer = LogStreamer()
        return _global_log_streamer


class GUIHandler(logging.Handler):
    """Logging handler that pushes messages to the GUI log streamer.
    
    This handler can be attached to any logger to stream its output
    to the Tkinter GUI console.
    """
    
    def __init__(self, streamer: Optional[LogStreamer] = None):
        super().__init__()
        self._streamer = streamer or get_log_streamer()
    
    def emit(self, record: logging.LogRecord) -> None:
        """Push log record to the streamer queue.
        
        Args:
            record: The log record to publish.
        """
        try:
            msg = self.format(record)
            self._streamer.publish(msg, record.levelname)
        except Exception:
            self.handleError(record)


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
        logger.setLevel(getattr(logging, level.upper(), logging.INFO))

        handler = logging.StreamHandler(sys.stderr)
        handler.setLevel(getattr(logging, level.upper(), logging.INFO))

        formatter = ColoredFormatter(
            "[%(asctime)s] %(levelname)s (%(name)s) - %(message)s",
            datefmt="%H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

        logger.propagate = False

    return logger


def setup_root_logger(level: str = "INFO") -> logging.Logger:
    """Setup root logger for the application.

    Args:
        level: Logging level

    Returns:
        Root logger instance
    """
    root_logger = logging.getLogger("web_contractor")
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    if not root_logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        formatter = ColoredFormatter(
            "[%(asctime)s] %(levelname)s - %(message)s",
            datefmt="%H:%M:%S",
        )
        handler.setFormatter(formatter)
        root_logger.addHandler(handler)

    return root_logger
