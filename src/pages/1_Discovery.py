"""Discovery Page - Lead Discovery Pipeline.

Note: Bucket management has been moved to the CLI.
Use `python scripts/manage_buckets.py` to create, list, or delete buckets.
"""

import streamlit as st
from database.repository import count_buckets, count_leads, get_all_buckets
from database.connection import get_connection_status, DatabaseUnavailableError
from infra.logging import get_logger
from ui.utils import get_app, check_db_status

logger = get_logger(__name__)

st.set_page_config(page_title="Discovery", layout="wide")

st.title("🔍 Lead Discovery")
st.caption("Run discovery pipelines with existing buckets. Use CLI for bucket management: `python scripts/manage_buckets.py`")

app = get_app()
db_ok = check_db_status()

if "discovery_running" not in st.session_state:
    st.session_state.discovery_running = False
if "discovery_result" not in st.session_state:
    st.session_state.discovery_result = None

buckets_count = None
total_leads = None
if db_ok:
    try:
        buckets_count = count_buckets()
        total_leads = count_leads()
    except DatabaseUnavailableError:
        db_ok = False

db_status = get_connection_status()

with st.sidebar:
    st.subheader("📊 Quick Stats")

    if db_status["connected"] and db_status["healthy"]:
        st.success("🟢 Database Connected")
    else:
        st.error("🔴 Database Disconnected")

    if not db_ok or buckets_count is None:
        st.warning("⚠️ Database unavailable — cannot fetch bucket count")
        st.metric("Total Buckets", "N/A")
    else:
        st.metric("Total Buckets", f"{buckets_count}")

    if not db_ok or total_leads is None:
        st.warning("⚠️ Database unavailable — cannot fetch lead count")
        st.metric("Total Leads", "N/A")
    else:
        st.metric("Total Leads", f"{total_leads:,}")

    st.divider()

    st.subheader("⚡ Quick Actions")
    st.info("📦 To manage buckets, use the CLI:\n```bash\npython scripts/manage_buckets.py\n```")

    if st.session_state.discovery_running:
        st.warning("⏳ Discovery in progress...")
        if st.button("⏹️ Cancel Discovery", type="secondary", use_container_width=True):
            st.session_state.discovery_running = False
            st.rerun()
    elif st.button("🚀 Run Discovery", type="primary", use_container_width=True):
        st.session_state.discovery_running = True
        st.session_state.discovery_result = None
        st.rerun()

# Main content - bucket selection and discovery run
buckets = get_all_buckets()

if not buckets:
    st.warning("📦 No buckets found. Create one using the CLI:")
    st.code("python scripts/manage_buckets.py --create --business-type 'dentists' --locations 'New York, Los Angeles'", language="bash")
    st.stop()

bucket_names = [b["name"] for b in buckets]

st.markdown("---")

col1, col2 = st.columns(2)
with col1:
    selected_bucket = st.selectbox(
        "Select Bucket",
        ["All Buckets"] + bucket_names,
    )
    bucket_name = None if selected_bucket == "All Buckets" else selected_bucket

with col2:
    max_queries = st.number_input(
        "Max Queries",
        min_value=1,
        max_value=100,
        value=20,
        step=5,
    )

st.markdown("---")

if st.session_state.discovery_running:
    st.warning("⏳ Discovery already in progress...")
    if st.button("Cancel", type="secondary"):
        st.session_state.discovery_running = False
        st.rerun()
elif st.button(
    "🚀 Run Discovery", type="primary", disabled=st.session_state.discovery_running
):
    st.session_state.discovery_running = True
    st.session_state.discovery_result = None

    with st.status("Running discovery...", expanded=True) as status:

        def progress_callback(current: int, total: int, message: str):
            status.update(label=f"Processing query {current}/{total}")

        try:
            result = app.scraper.run(
                bucket_name=bucket_name,
                max_queries=max_queries,
                progress_callback=progress_callback,
            )
            st.session_state.discovery_result = result
            status.update(
                label="✅ Discovery complete!",
                state="complete",
                expanded=False,
            )
        except Exception as e:
            st.session_state.discovery_result = {"error": str(e)}
            status.update(
                label=f"❌ Discovery failed: {e}",
                state="error",
                expanded=True,
            )
            logger.error(f"Discovery error: {e}")

    st.session_state.discovery_running = False

    if (
        st.session_state.discovery_result
        and "error" not in st.session_state.discovery_result
    ):
        result = st.session_state.discovery_result
        st.success(
            f"**{result['leads_saved']}** new leads saved "
            f"(from {result['leads_found']} found)"
        )
        col1, col2, col3 = st.columns(3)
        col1.metric("Queries Executed", result["queries_executed"])
        col2.metric("Leads Found", result["leads_found"])
        col3.metric("Leads Saved", result["leads_saved"])
    elif (
        st.session_state.discovery_result
        and "error" in st.session_state.discovery_result
    ):
        st.error(f"Discovery failed: {st.session_state.discovery_result['error']}")
