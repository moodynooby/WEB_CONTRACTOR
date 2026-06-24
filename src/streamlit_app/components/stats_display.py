"""Dashboard stat card component for Streamlit."""

import streamlit as st


def show_stats(stats: dict):
    """Display 4 stat cards in a row.

    Args:
        stats: Dict with 'Buckets', 'Pending Audits', 'Qualified Leads',
               'Emails for Review' keys.
    """
    cols = st.columns(4)
    labels = ["Buckets", "Pending Audits", "Qualified Leads", "Emails for Review"]
    for col, label in zip(cols, labels):
        with col:
            st.metric(label=label, value=stats.get(label, 0))
