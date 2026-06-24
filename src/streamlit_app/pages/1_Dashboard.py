"""Dashboard page - DB status and quick statistics."""

import streamlit as st
from services.stats_service import StatsService
from streamlit_app.components.stats_display import show_stats
from streamlit_app.components.log_viewer import show_log_viewer, clear_logs


def render():
    st.title("Dashboard")

    status = StatsService.get_db_status()
    connected = status.get("connected", False)
    db_name = status.get("database", "")

    col1, col2 = st.columns(2)
    with col1:
        if connected:
            db_label = f"Connected{f' ({db_name})' if db_name else ''}"
            st.success(f"Database: {db_label}")
        else:
            st.error("Database: Disconnected")

    stats = StatsService.get_stats()
    show_stats(stats)

    st.divider()
    col1, col2 = st.columns([4, 1])
    with col2:
        if st.button("Clear Log", use_container_width=True):
            clear_logs()
            st.rerun()
    show_log_viewer(height=400)


render()
