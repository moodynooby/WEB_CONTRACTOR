"""Streamlit session state utilities for ensuring app initialization."""

import streamlit as st
from core.app_core import WebContractorApp


def get_app() -> WebContractorApp:
    """Get or initialize the WebContractorApp from session state.
    
    Returns:
        The WebContractorApp instance from session state.
    """
    if "app" not in st.session_state:
        st.session_state.app = WebContractorApp()
        st.session_state.app.initialize()
    return st.session_state.app
