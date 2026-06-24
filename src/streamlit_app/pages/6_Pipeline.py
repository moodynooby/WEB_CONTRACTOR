"""Pipeline page - run full audit + email generation pipeline."""

import threading
import time

import streamlit as st
from services.stats_service import StatsService
from streamlit_app.components.log_viewer import append_log, show_log_viewer, clear_logs
from streamlit_app.state import init_session_state, PROGRESS_STATUS_RUNNING, PROGRESS_STATUS_DONE, PROGRESS_STATUS_ERROR

init_session_state()


def _run_full_pipeline_bg(progress: dict, limit: int) -> None:
    from app import WebContractorApp
    app = WebContractorApp()
    app.initialize()
    try:
        def on_progress(current, total, msg):
            progress["current"] = current
            progress["total"] = total
            progress["message"] = msg
        result = app.run_unified_pipeline(limit=limit, progress_callback=on_progress)
        progress["status"] = PROGRESS_STATUS_DONE
        progress["result"] = result
    except Exception as e:
        progress["status"] = PROGRESS_STATUS_ERROR
        progress["error"] = str(e)
    finally:
        app.shutdown()


def render():
    st.title("Full Pipeline")

    if not StatsService.is_connected():
        st.error("Database not connected.")
        return

    progress = st.session_state.pipeline_full
    is_running = progress.get("status") == PROGRESS_STATUS_RUNNING

    col1, col2 = st.columns([2, 1])
    with col1:
        st.info(
            "Runs the full pipeline: audit qualified leads → generate emails → "
            "ready for review. Does NOT include discovery or sending."
        )
        limit = st.number_input("Pipeline Limit", min_value=1, max_value=200, value=20, disabled=is_running)
    with col2:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button(
            "Run Full Pipeline",
            type="primary",
            disabled=is_running,
            use_container_width=True,
        ):
            progress["status"] = PROGRESS_STATUS_RUNNING
            progress["message"] = "Starting full pipeline..."
            threading.Thread(target=_run_full_pipeline_bg, args=(progress, int(limit)), daemon=True).start()
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
                status.update(label="Pipeline Complete", state="complete")
                bar.progress(1.0, text="Done")
                result = progress.get("result", {})
                if result:
                    st.success(f"Pipeline finished: {result}")
                    append_log(f"Full pipeline completed: {result}")
                StatsService.get_stats()
                progress["status"] = "idle"
                st.rerun()
            elif progress.get("status") == PROGRESS_STATUS_ERROR:
                status.update(label="Pipeline Failed", state="error")
                bar.progress(1.0, text="Failed")
                st.error(progress.get("error", "Unknown error"))
                append_log(f"Full pipeline failed: {progress.get('error')}")
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
