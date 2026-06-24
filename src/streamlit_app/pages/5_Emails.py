"""Emails page - generate and review outreach emails."""

import sys
import time
from pathlib import Path

SRC_DIR = Path(__file__).parent.parent.parent.resolve()
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import streamlit as st
from services.email_service import EmailService
from services.pipeline_service import PipelineService, PROGRESS_STATUS_RUNNING, PROGRESS_STATUS_DONE, PROGRESS_STATUS_ERROR
from services.stats_service import StatsService
from streamlit_app.components.email_card import show_email_card
from streamlit_app.components.log_viewer import append_log, show_log_viewer
from streamlit_app.state import init_session_state

init_session_state()

email_service = EmailService()


def render():
    st.title("Email Generation & Review")

    if not StatsService.is_connected():
        st.error("Database not connected.")
        return

    tab1, tab2 = st.tabs(["Generate Emails", "Review Emails"])

    with tab1:
        st.subheader("Generate Emails for Qualified Leads")
        progress = st.session_state.pipeline_email
        is_running = progress.get("status") == PROGRESS_STATUS_RUNNING

        st.info("Generates personalized cold emails for qualified leads using AI.")
        limit = st.number_input("Generation Limit", min_value=1, max_value=200, value=20, disabled=is_running, key="gen_limit")

        if st.button(
            "Generate Emails",
            type="primary",
            disabled=is_running,
            use_container_width=True,
        ):
            progress["status"] = PROGRESS_STATUS_RUNNING
            progress["message"] = "Starting email generation..."
            PipelineService.generate_emails(progress, limit=int(limit))
            st.rerun()

        if is_running:
            with st.status(progress.get("message", "Running..."), expanded=True) as status:
                bar = st.progress(0, text=progress.get("message", ""))
                while progress.get("status") == PROGRESS_STATUS_RUNNING:
                    current = progress.get("current", 0)
                    total = progress.get("total", 1)
                    pct = min(current / max(total, 1), 1.0)
                    bar.progress(pct, text=progress.get("message", ""))
                    st.rerun()
                    time.sleep(0.5)

                if progress.get("status") == PROGRESS_STATUS_DONE:
                    status.update(label="Generation Complete", state="complete")
                    bar.progress(1.0, text="Done")
                    result = progress.get("result", {})
                    if result:
                        st.success(f"Generation finished: {result}")
                        append_log(f"Email generation completed: {result}")
                    StatsService.get_stats()
                    progress["status"] = "idle"
                    st.rerun()
                elif progress.get("status") == PROGRESS_STATUS_ERROR:
                    status.update(label="Generation Failed", state="error")
                    st.error(progress.get("error", "Unknown error"))
                    append_log(f"Email generation failed: {progress.get('error')}")
                    progress["status"] = "idle"
                    st.rerun()

    with tab2:
        st.subheader("Review Generated Emails")

        col1, col2 = st.columns([1, 1])
        with col1:
            review_limit = st.number_input("Limit", min_value=1, max_value=200, value=50, key="review_limit")
        with col2:
            st.button("Refresh", use_container_width=True)

        emails = email_service.get_emails(limit=int(review_limit))

        if not emails:
            st.info("No emails pending review. Run email generation first.")
            show_log_viewer(height=300)
            return

        st.caption(f"{len(emails)} email(s) to review")

        if st.button("Approve All", type="secondary", use_container_width=True):
            count = email_service.approve_all(emails)
            st.success(f"Approved {count} email(s)")
            append_log(f"Approved {count} emails")
            st.rerun()

        st.divider()

        for email in emails:
            cid = email["id"]

            if st.session_state.get("confirmed_delete_email") == cid:
                col_del, col_cancel = st.columns(2)
                with col_del:
                    if st.button("Confirm Delete", key=f"confirm_del_{cid}"):
                        email_service.delete(cid)
                        st.session_state.confirmed_delete_email = None
                        append_log(f"Deleted email for {email.get('business_name', '')}")
                        st.rerun()
                with col_cancel:
                    if st.button("Cancel", key=f"cancel_del_{cid}"):
                        st.session_state.confirmed_delete_email = None
                        st.rerun()
                st.divider()
                continue

            show_email_card(email, email_service)

        show_log_viewer(height=300)


render()
