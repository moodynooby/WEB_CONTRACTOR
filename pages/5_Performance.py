"""Performance Page - Query Performance Analytics."""

import streamlit as st
import pandas as pd
from core.db_models import QueryPerformance
from core import db
from core.logging import get_logger

logger = get_logger(__name__)

st.title("📊 Query Performance")
st.caption("Monitor query efficiency and identify stale queries")

with db:
    query_perf = QueryPerformance.select().dicts()
    perf_df = pd.DataFrame(query_perf)

if perf_df.empty:
    st.info("No query performance data yet. Run discovery first.")
else:
    st.subheader("📈 Overview")
    col1, col2, col3, col4 = st.columns(4)
    
    col1.metric("Total Queries", len(perf_df))
    col2.metric("Active Queries", len(perf_df[perf_df["is_active"]]))
    col3.metric("Inactive Queries", len(perf_df[~perf_df["is_active"]]))
    col4.metric(
        "Avg Success Rate",
        f"{(perf_df['total_leads_saved'].sum() / max(perf_df['total_executions'].sum(), 1) * 100):.1f}%",
    )

    col1, col2 = st.columns(2)
    with col1:
        status_filter = st.radio(
            "Query Status",
            ["All", "Active", "Inactive"],
            horizontal=True,
        )
    
    with col2:
        min_executions = st.slider("Min Executions", 0, 50, 1)

    if status_filter == "Active":
        filtered = perf_df[perf_df["is_active"]]
    elif status_filter == "Inactive":
        filtered = perf_df[~perf_df["is_active"]]
    else:
        filtered = perf_df
    
    filtered = filtered[filtered["total_executions"] >= min_executions]

    filtered = filtered.copy()
    filtered["success_rate"] = (
        filtered["total_leads_saved"] / filtered["total_executions"].clip(lower=1) * 100
    ).round(1)

    st.subheader("📋 Query Performance Details")
    st.dataframe(
        filtered[[
            "query_pattern",
            "city",
            "is_active",
            "total_executions",
            "total_leads_found",
            "total_leads_saved",
            "consecutive_failures",
            "success_rate",
        ]],
        use_container_width=True,
        height=500,
    )

    st.subheader("📉 Analytics")
    
    col1, col2 = st.columns(2)
    with col1:
        st.bar_chart(
            filtered.groupby("is_active")["total_executions"].sum(),
            horizontal=True,
        )
        st.caption("Total executions by active/inactive status")
    
    with col2:
        st.bar_chart(
            filtered.nlargest(10, "total_leads_saved")[["query_pattern", "total_leads_saved"]].set_index("query_pattern"),
            horizontal=True,
        )
        st.caption("Top 10 queries by leads saved")

    stale = perf_df[perf_df["consecutive_failures"] >= 3]
    if not stale.empty:
        st.subheader("⚠️ Stale Queries (3+ consecutive failures)")
        st.dataframe(
            stale[[
                "query_pattern",
                "city",
                "consecutive_failures",
                "total_executions",
            ]],
            use_container_width=True,
        )
