"""Web Contractor - Streamlit Web UI Entry Point."""

import hashlib
import traceback

import streamlit as st
from core.app_core import WebContractorApp

st.set_page_config(
    page_title="Web Contractor",
    page_icon="🏗️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Authentication ──────────────────────────────────────────────────────
VALID_USERNAME = "admin"
VALID_PASSWORD_HASH = hashlib.sha256("changeme".encode()).hexdigest()


def show_login() -> bool:
    """Show login form and return True if authenticated."""
    st.title("🔐 Web Contractor Login")

    with st.form("login_form"):
        username = st.text_input("Username", autocomplete="username")
        password = st.text_input("Password", type="password", autocomplete="current-password")
        submitted = st.form_submit_button("Login", use_container_width=True)

        if submitted:
            if username and password:
                pwd_hash = hashlib.sha256(password.encode()).hexdigest()
                if username == VALID_USERNAME and pwd_hash == VALID_PASSWORD_HASH:
                    st.session_state["logged_in"] = True
                    st.session_state["username"] = username
                    st.rerun()
                else:
                    st.error("Invalid username or password")
            else:
                st.error("Please enter both username and password")

    return False


if not st.session_state.get("logged_in"):
    show_login()
    st.stop()

# Authenticated UI
with st.sidebar:
    st.caption(f"👤 Logged in as: **{st.session_state.get('username', 'User')}**")
    if st.button("🚪 Logout", use_container_width=True):
        st.session_state.pop("logged_in", None)
        st.session_state.pop("username", None)
        st.rerun()


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
