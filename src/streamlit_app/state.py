"""Session state management for Streamlit app.

Centralizes all session_state key definitions and initialization.
"""

import streamlit as st
from services.pipeline_service import make_progress_dict


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
