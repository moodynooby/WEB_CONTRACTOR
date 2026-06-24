"""Discovery page - run lead discovery pipeline."""

import streamlit as st
from services.pipeline_service import PipelineService, PROGRESS_STATUS_RUNNING, PROGRESS_STATUS_DONE, PROGRESS_STATUS_ERROR
from services.stats_service import StatsService
from streamlit_app.components.log_viewer import append_log, show_log_viewer, clear_logs
from streamlit_app.state import init_session_state

init_session_state()


def render():
    st.title("Lead Discovery")

    if not StatsService.is_connected():
        st.error("Database not connected.")
        return

    progress = st.session_state.pipeline_discovery
    is_running = progress.get("status") == PROGRESS_STATUS_RUNNING

    col1, col2 = st.columns([2, 1])
    with col1:
        st.info(
            "Searches multiple sources (Google Maps, JustDial, YellowPages, Blogspot, WordPress, Wix, Sulekha) "
            "for businesses matching your buckets."
        )
    with col2:
        disabled = is_running or st.session_state.get("pipeline_busy", False)

        if st.button(
            "Run Discovery",
            type="primary",
            disabled=disabled,
            use_container_width=True,
        ):
            progress["status"] = PROGRESS_STATUS_RUNNING
            progress["message"] = "Starting discovery..."
            PipelineService.run_discovery(progress)
            st.rerun()

    if is_running:
        with st.status(progress.get("message", "Running..."), expanded=True) as status:
            bar = st.progress(0, text=progress.get("message", ""))
            placeholder = st.empty()

            while progress.get("status") == PROGRESS_STATUS_RUNNING:
                current = progress.get("current", 0)
                total = progress.get("total", 1)
                pct = min(current / max(total, 1), 1.0)
                bar.progress(pct, text=progress.get("message", ""))
                placeholder.info(f"Progress: {current}/{total}")
                st.rerun()
                import time
                time.sleep(0.5)

            if progress.get("status") == PROGRESS_STATUS_DONE:
                status.update(label="Discovery Complete", state="complete")
                bar.progress(1.0, text="Done")
                result = progress.get("result", {})
                if result:
                    st.success(f"Discovery finished: {result}")
                    append_log(f"Discovery completed: {result}")
                StatsService.get_stats()
                progress["status"] = "idle"
                st.rerun()
            elif progress.get("status") == PROGRESS_STATUS_ERROR:
                status.update(label="Discovery Failed", state="error")
                bar.progress(1.0, text="Failed")
                st.error(progress.get("error", "Unknown error"))
                append_log(f"Discovery failed: {progress.get('error')}")
                progress["status"] = "idle"
                st.rerun()

    st.divider()
    col1, col2 = st.columns([4, 1])
    with col2:
        if st.button("Clear Log", use_container_width=True):
            clear_logs()
            st.rerun()
    show_log_viewer(height=400)


render()
