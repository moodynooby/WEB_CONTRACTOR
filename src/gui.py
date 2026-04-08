"""Web Contractor - Streamlit Web UI Entry Point

Unified application layer with business logic and UI.
"""
import streamlit as st
from app import App


st.set_page_config(
    page_title="Web Contractor",
    page_icon="🏗️",
    layout="wide",
    initial_sidebar_state="expanded",
)



def setup_global_error_handler():
    """Initialize global error tracking in session state."""
    if "app_errors" not in st.session_state:
        st.session_state.app_errors = []


setup_global_error_handler()

if "app" not in st.session_state:
    st.session_state.app = App()
    st.session_state.app.initialize()


def _on_session_end():
    """Shut down app and close database connection when Streamlit session ends."""
    if "app" in st.session_state:
        st.session_state.app.shutdown()


_session_end_event = getattr(st, "events", None)
if _session_end_event is not None:
    _session_end_event.session_end.connect(_on_session_end)

pg = st.navigation(
    [
        st.Page("pages/0_Pipeline.py", title="🏗️ Pipeline"),
        st.Page("pages/1_Discovery.py", title="🔍 Discovery"),
        st.Page("pages/2_Audit.py", title="📋 Audit"),
        st.Page("pages/3_Email.py", title="📧 Email"),
        st.Page("pages/4_Analytics.py", title="📊 Analytics"),
    ]
)

pg.run()
