"""Streamlit session state utilities for ensuring app initialization."""

import streamlit as st
from app import App
from database.connection import is_connected


def get_app() -> App:
    """Get or initialize the App from session state.

    Returns:
        The App instance from session state.
        Note: App initializes regardless of DB status; individual DB operations
        will raise DatabaseUnavailableError if the connection is down.
    """
    if "app" not in st.session_state:
        st.session_state.app = App()
        st.session_state.app.initialize()
    return st.session_state.app


def check_db_status() -> bool:
    """Check database connection and show error banner if unavailable.

    Returns:
        True if DB is connected, False otherwise.
        When False, the caller should handle the degraded state.
    """
    if not is_connected():
        st.error(
            "🔴 **Database Unavailable** — All database-dependent features are disabled. "
            "Set `MONGODB_URI` in your `.env` file and restart."
        )
        return False
    return True
