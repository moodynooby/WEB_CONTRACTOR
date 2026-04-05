"""Standard Python Logging Setup for Web Contractor.

Provides a unified logging configuration across all modules.
No file logging - logs go to console (stderr) only.
"""

import logging
import sys


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
