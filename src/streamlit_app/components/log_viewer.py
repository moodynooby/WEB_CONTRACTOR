"""Log viewer component for Streamlit.

Maintains a rolling list of log lines in session state.
"""

import streamlit as st


def append_log(message: str):
    """Append a log message to the shared log buffer."""
    if "log_lines" not in st.session_state:
        st.session_state.log_lines = []
    st.session_state.log_lines.append(message)
    if len(st.session_state.log_lines) > 500:
        st.session_state.log_lines = st.session_state.log_lines[-500:]


def show_log_viewer(height: int = 300):
    """Display the log console as a scrollable text area.

    Args:
        height: Height of the text area in pixels.
    """
    lines = st.session_state.get("log_lines", [])
    text = "\n".join(lines) if lines else "No logs yet."
    st.text_area("Log Console", value=text, height=height, disabled=True, key="log_viewer")


def clear_logs():
    """Clear all accumulated log lines."""
    st.session_state.log_lines = []
