"""Web Contractor - Streamlit Web UI Entry Point."""

import traceback
import streamlit as st
from core.app_core import WebContractorApp
from core.mode_manager import get_mode_manager

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


def handle_app_exception(func):
    """Decorator to handle exceptions gracefully in Streamlit pages."""

    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            error_msg = str(e)
            tb = traceback.format_exc()

            st.session_state.app_errors.append(
                {
                    "error": error_msg,
                    "traceback": tb,
                }
            )

            st.error(f"⚠️ An error occurred: {error_msg}")
            with st.expander("📋 Error Details (for debugging)"):
                st.code(tb, language="python")
            return None

    return wrapper


def run_safe_operation(operation_name: str, operation_func, *args, **kwargs):
    """Run an operation with error handling and progress feedback.

    Args:
        operation_name: Name of the operation for display
        operation_func: The function to execute
        *args, **kwargs: Arguments to pass to the operation

    Returns:
        Tuple of (success: bool, result: Any)
    """
    placeholder = st.empty()
    try:
        with st.spinner(f"⚙️ {operation_name}..."):
            result = operation_func(*args, **kwargs)
        return True, result
    except Exception as e:
        error_msg = f"{operation_name} failed: {str(e)}"
        tb = traceback.format_exc()

        st.session_state.app_errors.append(
            {
                "error": error_msg,
                "traceback": tb,
            }
        )

        placeholder.error(f"❌ {error_msg}")
        with st.expander("📋 Error Details"):
            st.code(tb, language="python")
        return False, None


setup_global_error_handler()

if "app" not in st.session_state:
    st.session_state.app = WebContractorApp()
    st.session_state.app.initialize()

with st.sidebar:
    st.markdown("---")
    mode_mgr = get_mode_manager()
    current_mode = mode_mgr.get_current_mode()

    mode_icon = "☁️" if not current_mode["is_local"] else "🖥️"
    mode_label = (
        "Cloud"
        if not current_mode["is_local"]
        else f"Local ({current_mode['local_provider']})"
    )
    perf_mode = current_mode["profile"]

    st.markdown(f"### {mode_icon} {mode_label}")
    st.markdown(f"**{perf_mode['icon']} {perf_mode['label']}**")
    st.caption(f"Hardware: {current_mode['hardware'].replace('_', ' ').upper()}")

    st.markdown("---")
    st.caption("💡 Configure modes in Pipeline page → LLM Mode & Performance Settings")

pg = st.navigation(
    [
        st.Page("pages/0_Pipeline.py", title="🏗️ Pipeline"),
        st.Page("pages/1_Discovery.py", title="🔍 Discovery"),
        st.Page("pages/2_Audit.py", title="📋 Audit"),
        st.Page("pages/3_Email.py", title="📧 Email"),
        st.Page("pages/5_Performance.py", title="📊 Performance"),
    ]
)

pg.run()
