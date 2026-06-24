"""Buckets page - create, list, and delete discovery buckets."""

import sys
from pathlib import Path

SRC_DIR = Path(__file__).parent.parent.parent.resolve()
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import streamlit as st
from services.bucket_service import BucketService
from services.stats_service import StatsService
from streamlit_app.components.log_viewer import append_log
from streamlit_app.state import init_session_state

init_session_state()


def render():
    st.title("Buckets")

    if not StatsService.is_connected():
        st.error("Database not connected.")
        return

    tab1, tab2 = st.tabs(["Create Bucket", "Manage Buckets"])

    with tab1:
        st.subheader("Create New Bucket")
        with st.form("create_bucket_form"):
            business_type = st.text_input(
                "Business Type",
                placeholder="e.g., dentists, yoga studios, plumbers",
                help="Type of business to target",
            )
            target_locations = st.text_area(
                "Target Locations",
                placeholder="e.g., Mumbai, Delhi, Bangalore (one per line)",
                help="Cities or regions to target (one per line)",
            )
            col1, col2 = st.columns(2)
            with col1:
                max_queries = st.number_input("Max Queries", min_value=1, value=10, help="Maximum queries per run")
            with col2:
                max_results = st.number_input("Max Results", min_value=1, value=50, help="Maximum results per query")

            submitted = st.form_submit_button("Generate & Create", use_container_width=True)

            if submitted:
                if not business_type.strip():
                    st.error("Business type is required.")
                elif not target_locations.strip():
                    st.error("At least one target location is required.")
                else:
                    locations = [loc.strip() for loc in target_locations.strip().split("\n") if loc.strip()]
                    with st.spinner("Generating bucket configuration via AI..."):
                        success, message = BucketService.create(
                            business_type=business_type.strip(),
                            target_locations=locations,
                            max_queries=int(max_queries),
                            max_results=int(max_results),
                        )
                    if success:
                        st.success(message)
                        append_log(f"Bucket created: {business_type}")
                        st.rerun()
                    else:
                        st.error(message)

    with tab2:
        st.subheader("Existing Buckets")
        buckets = BucketService.list()

        if not buckets:
            st.info("No buckets created yet. Use the Create tab to add one.")
            return

        for bucket in buckets:
            with st.container():
                st.markdown(
                    f"""
                    <div style="
                        background-color: #1e1e1e;
                        border: 1px solid #333;
                        border-radius: 8px;
                        padding: 12px;
                        margin-bottom: 8px;
                    ">
                        <strong style="color:#fcfcfc; font-size:16px;">{bucket.get('name', 'Unnamed')}</strong>
                        <span style="color:#aaa; font-size:12px; margin-left:12px;">
                            Priority: {bucket.get('priority', '-')} |
                            Target: {bucket.get('monthly_target', '-')}/mo |
                            Categories: {len(bucket.get('categories', []))} |
                            Patterns: {len(bucket.get('search_patterns', []))}
                        </span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                with st.expander("Details"):
                    st.json(bucket)

                if st.button("Delete", key=f"del_bucket_{bucket.get('id')}"):
                    st.session_state.confirmed_delete_bucket = bucket.get("id")
                    st.rerun()

            bucket_id: str | None = bucket.get("id")
            if bucket_id and st.session_state.get("confirmed_delete_bucket") == bucket_id:
                st.warning(f"Delete bucket '{bucket.get('name')}'? This will also remove related leads and query data.")
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("Yes, Delete", key=f"confirm_del_{bucket_id}"):
                        success, msg = BucketService.delete(bucket_id, cascade=True)
                        if success:
                            st.success(msg)
                            append_log(f"Deleted bucket: {bucket.get('name')}")
                        else:
                            st.error(msg)
                        st.session_state.confirmed_delete_bucket = None
                        st.rerun()
                with col2:
                    if st.button("Cancel", key=f"cancel_del_{bucket.get('id')}"):
                        st.session_state.confirmed_delete_bucket = None
                        st.rerun()

            st.divider()


render()
