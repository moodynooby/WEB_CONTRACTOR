"""Web Contractor - Streamlit Web Application.

Entry point: streamlit run src/streamlit_app/Home.py
"""

import sys
from pathlib import Path

# Ensure src/ is on sys.path so imports work
SRC_DIR = Path(__file__).parent.parent.resolve()
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import streamlit as st
from infra.logging import get_logger
from database.connection import init_db, is_connected
from streamlit_app.state import init_session_state

logger = get_logger(__name__)

st.set_page_config(
    page_title="Web Contractor",
    page_icon="🌐",
    layout="wide",
    initial_sidebar_state="expanded",
)

init_session_state()


def init_app():
    """Initialize database and services once per session."""
    if st.session_state.get("initialized"):
        return

    with st.spinner("Initializing database connection..."):
        try:
            init_db()
            st.session_state.initialized = True
            logger.info("Streamlit app initialized")
        except Exception as e:
            logger.error(f"Initialization failed: {e}")
            st.error(f"Failed to initialize: {e}")


def main():
    init_app()

    st.sidebar.title("Web Contractor")
    st.sidebar.markdown("---")

    db_ok = is_connected()
    if db_ok:
        st.sidebar.success("Database Connected")
    else:
        st.sidebar.error("Database Disconnected")

    pages = {
        "Dashboard": "pages/1_Dashboard.py",
        "Buckets": "pages/2_Buckets.py",
        "Discovery": "pages/3_Discovery.py",
        "Audit": "pages/4_Audit.py",
        "Emails": "pages/5_Emails.py",
        "Pipeline": "pages/6_Pipeline.py",
    }

    page = st.sidebar.radio("Navigation", list(pages.keys()))
    st.sidebar.markdown("---")

    st.sidebar.caption("Web Contractor v1")
    st.sidebar.caption("Headless-friendly web UI")

    # Execute the selected page
    page_file = Path(__file__).parent / pages[page]
    page_code = page_file.read_text(encoding="utf-8")

    # Extract the render() call and execute in context
    exec(page_code, {"st": st, "__file__": str(page_file)})


if __name__ == "__main__":
    main()
