"""Database package for Web Contractor."""

from database.connection import (
    init_db,
    close_db,
    is_connected,
    is_initialized,
    is_healthy,
    get_database,
    get_client,
    get_connection_status,
    DatabaseUnavailableError,
)

__all__ = [
    "init_db",
    "close_db",
    "is_connected",
    "is_initialized",
    "is_healthy",
    "get_database",
    "get_client",
    "get_connection_status",
    "DatabaseUnavailableError",
]
