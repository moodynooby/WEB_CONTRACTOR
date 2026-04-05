"""Discovery Page - Lead Discovery Pipeline."""

import streamlit as st
from core import get_all_buckets
from core.logging import get_logger
from core.streamlit_utils import get_app

logger = get_logger(__name__)

st.title("🔍 Lead Discovery")
st.caption("Generate search queries and scrape leads from configured buckets")

app = get_app()

if "discovery_running" not in st.session_state:
    st.session_state.discovery_running = False
if "discovery_result" not in st.session_state:
    st.session_state.discovery_result = None

buckets = get_all_buckets()
bucket_names = [b["name"] for b in buckets]

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

with st.expander("ℹ️ About Discovery"):
    st.markdown(
        """
    Discovery pipeline:
    1. **Query Generation**: Creates search queries from bucket patterns + cities
    2. **Parallel Scraping**: Runs enabled sources in parallel for each query
    3. **Deduplication**: Filters out leads where website already exists
    4. **Save**: Stores new leads to database with bucket and source info
    
    Stale queries (3+ consecutive failures) are automatically disabled.
    """
    )
