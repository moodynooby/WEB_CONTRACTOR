"""Streamlit session state utilities for ensuring app initialization."""

import streamlit as st
from gui import App


def get_app() -> App:
    """Get or initialize the App from session state.

    Returns:
        The App instance from session state.
    """
    if "app" not in st.session_state:
        st.session_state.app = App()
        st.session_state.app.initialize()
    return st.session_state.app
