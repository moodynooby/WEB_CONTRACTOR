"""Database package for Web Contractor."""

from database.connection import (
    init_db,
    close_db,
    is_connected,
    get_database,
    get_connection_status,
    DatabaseUnavailableError,
)

__all__ = [
    "init_db",
    "close_db",
    "is_connected",
    "get_database",
    "get_connection_status",
    "DatabaseUnavailableError",
]
