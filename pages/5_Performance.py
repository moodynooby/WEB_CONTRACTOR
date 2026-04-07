"""Performance Page — Query Performance Analytics with auto-refresh support."""


import streamlit as st
import pandas as pd
from core.repository import get_query_performance_all
from core.logging import get_logger

logger = get_logger(__name__)

st.set_page_config(layout="wide")

# ── Auto-refresh toggle ─────────────────────────────────────────────────
if "auto_refresh" not in st.session_state:
    st.session_state.auto_refresh = False
if "refresh_interval" not in st.session_state:
    st.session_state.refresh_interval = 30

with st.sidebar:
    st.subheader("🔄 Auto-Refresh")
    st.session_state.auto_refresh = st.toggle(
        "Enable auto-refresh",
        value=st.session_state.auto_refresh,
        help="Automatically refresh this page to see live stats",
    )
    if st.session_state.auto_refresh:
        st.session_state.refresh_interval = st.selectbox(
            "Interval (seconds)",
            options=[10, 30, 60, 120, 300],
            index=1,
            key="refresh_interval_select",
        )
        st.caption(f"Refreshing every {st.session_state.refresh_interval}s")

        # Meta-refresh via HTML
        st.html(
            f'<meta http-equiv="refresh" content="{st.session_state.refresh_interval}">'
        )
    else:
        if st.button("🔄 Refresh Now"):
            st.rerun()

st.title("📊 Query Performance")
st.caption("Monitor query efficiency and identify stale queries")

perf_data = get_query_performance_all()
perf_df = pd.DataFrame(perf_data)

if perf_df.empty:
    st.info("No query performance data yet. Run discovery first.")
else:
    if "last_executed_at" in perf_df.columns:
        perf_df["last_executed_at"] = pd.to_datetime(
            perf_df["last_executed_at"], errors="coerce"
        )
    if "created_at" in perf_df.columns:
        perf_df["created_at"] = pd.to_datetime(perf_df["created_at"], errors="coerce")

    perf_df["success_rate"] = (
        perf_df["total_leads_saved"] / perf_df["total_executions"].clip(lower=1) * 100
    ).round(1)

    st.subheader("📈 Key Metrics")

    col1, col2, col3, col4, col5 = st.columns(5)

    col1.metric("Total Queries", len(perf_df))
    col2.metric("Active Queries", len(perf_df[perf_df["is_active"]]))
    col3.metric("Inactive Queries", len(perf_df[~perf_df["is_active"]]))
    col4.metric(
        "Avg Success Rate",
        f"{(perf_df['total_leads_saved'].sum() / max(perf_df['total_executions'].sum(), 1) * 100):.1f}%",
    )
    col5.metric(
        "Total Leads Saved",
        f"{perf_df['total_leads_saved'].sum():,}",
    )

    st.subheader("🔍 Filter")

    col1, col2 = st.columns(2)
    with col1:
        active_filter = st.multiselect(
            "Status",
            options=["Active", "Inactive"],
            default=["Active", "Inactive"],
        )

    with col2:
        min_executions = st.number_input(
            "Min Executions", min_value=0, max_value=1000, value=0
        )

    filtered = perf_df[
        perf_df["is_active"].isin([s == "Active" for s in active_filter])
    ]
    if min_executions > 0:
        filtered = filtered[filtered["total_executions"] >= min_executions]

    st.write(f"**{len(filtered)}** queries shown")

    tab1, tab2 = st.tabs(["📊 Table", "📈 Analytics"])

    with tab1:
        display_cols = [
            "query_pattern",
            "city",
            "is_active",
            "total_executions",
            "total_leads_found",
            "success_rate",
            "consecutive_failures",
        ]
        st.dataframe(
            filtered[display_cols]
            if all(c in filtered.columns for c in display_cols)
            else filtered,
            use_container_width=True,
        )

    with tab2:
        st.bar_chart(
            filtered.head(10).set_index("query_pattern")["success_rate"]
            if "query_pattern" in filtered.columns
            and "success_rate" in filtered.columns
            else filtered[["success_rate"]].head(10)
        )
