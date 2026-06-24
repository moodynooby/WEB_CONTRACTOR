"""Session state management for Streamlit app.

Centralizes all session state key definitions and initialization.
"""

import streamlit as st

PROGRESS_STATUS_IDLE = "idle"
PROGRESS_STATUS_RUNNING = "running"
PROGRESS_STATUS_DONE = "done"
PROGRESS_STATUS_ERROR = "error"


def make_progress_dict() -> dict:
    """Create a fresh progress dict for pipeline tracking."""
    return {
        "status": PROGRESS_STATUS_IDLE,
        "message": "",
        "current": 0,
        "total": 0,
        "result": None,
        "error": None,
    }


def init_session_state():
    """Initialize all session state variables on first run."""
    keys = {
        "initialized": False,
        "pipeline_discovery": make_progress_dict(),
        "pipeline_audit": make_progress_dict(),
        "pipeline_email": make_progress_dict(),
        "pipeline_full": make_progress_dict(),
        "confirmed_delete_email": None,
        "confirmed_delete_bucket": None,
        "log_lines": [],
    }
    for key, default in keys.items():
        if key not in st.session_state:
            st.session_state[key] = default
