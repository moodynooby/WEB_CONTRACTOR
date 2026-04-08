"""Analytics Page — Unified Dashboard with Lead, Email, Query & Bucket Insights."""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from database.repository import (
    get_all_leads,
    get_email_campaigns,
    get_query_performance_all,
)
from infra.logging import get_logger

logger = get_logger(__name__)

st.set_page_config(page_title="Analytics", layout="wide")

# --- Sidebar ---
with st.sidebar:
    st.subheader("🔄 Auto-Refresh")
    auto_refresh = st.toggle(
        "Enable",
        value=False,
        help="Automatically refresh to see live stats",
    )
    if auto_refresh:
        interval = st.selectbox(
            "Interval (seconds)",
            options=[10, 30, 60, 120, 300],
            index=1,
        )
        st.caption(f"Refreshing every {interval}s")
        st.html(f'<meta http-equiv="refresh" content="{interval}">')
    else:
        if st.button("🔄 Refresh Now", use_container_width=True):
            st.rerun()

    st.divider()
    if st.button("📥 Export Summary", use_container_width=True):
        with st.spinner("Preparing export..."):
            leads = get_all_leads(limit=10000)
            campaigns = get_email_campaigns(limit=5000)
            queries = get_query_performance_all()
            import io
            buf = io.StringIO()
            buf.write("=== LEADS SUMMARY ===\n")
            leads_df = pd.DataFrame(leads)
            if not leads_df.empty:
                buf.write(f"Total leads: {len(leads_df)}\n")
                buf.write(f"By status:\n{leads_df['status'].value_counts().to_string()}\n\n")
            buf.write("=== EMAIL CAMPAIGNS ===\n")
            camp_df = pd.DataFrame(campaigns)
            if not camp_df.empty:
                buf.write(f"Total campaigns: {len(camp_df)}\n")
                buf.write(f"By status:\n{camp_df['status'].value_counts().to_string()}\n\n")
            buf.write("=== QUERY PERFORMANCE ===\n")
            q_df = pd.DataFrame(queries)
            if not q_df.empty:
                buf.write(f"Total queries: {len(q_df)}\n")
                buf.write(f"Active: {q_df['is_active'].sum()}, Inactive: {(~q_df['is_active']).sum()}\n")
            st.download_button(
                "⬇️ Download Summary",
                data=buf.getvalue(),
                file_name="analytics_summary.txt",
                mime="text/plain",
                use_container_width=True,
            )

# --- Title ---
st.title("📊 Analytics Dashboard")
st.caption("Unified view of lead discovery, audit, email, and query performance")

# --- Fetch Data ---
with st.spinner("Loading analytics..."):
    leads = get_all_leads(limit=10000)
    campaigns = get_email_campaigns(limit=5000)
    queries = get_query_performance_all()

leads_df = pd.DataFrame(leads)
camp_df = pd.DataFrame(campaigns)
query_df = pd.DataFrame(queries)

if leads_df.empty and camp_df.empty and query_df.empty:
    st.info("No data available yet. Run the pipeline first to populate data.")
    st.stop()

# --- Parse timestamps ---
if not leads_df.empty:
    if "created_at" in leads_df.columns:
        leads_df["created_at"] = pd.to_datetime(leads_df["created_at"], errors="coerce")
if not camp_df.empty:
    for col in ["sent_at", "opened_at", "clicked_at", "replied_at"]:
        if col in camp_df.columns:
            camp_df[col] = pd.to_datetime(camp_df[col], errors="coerce")
if not query_df.empty:
    if "last_executed_at" in query_df.columns:
        query_df["last_executed_at"] = pd.to_datetime(query_df["last_executed_at"], errors="coerce")

# --- Tabs ---
tab_overview, tab_leads, tab_email, tab_queries = st.tabs([
    "📊 Overview",
    "🔍 Leads",
    "📧 Email Campaigns",
    "⚡ Query Performance",
])

# ===== OVERVIEW TAB =====
with tab_overview:
    # KPI cards
    total_leads = len(leads_df) if not leads_df.empty else 0
    qualified = (leads_df["status"] == "qualified").sum() if not leads_df.empty and "status" in leads_df.columns else 0
    total_campaigns = len(camp_df) if not camp_df.empty else 0
    emails_sent = (camp_df["status"] == "sent").sum() if not camp_df.empty and "status" in camp_df.columns else 0
    active_queries = query_df["is_active"].sum() if not query_df.empty and "is_active" in query_df.columns else 0
    avg_audit_score = round(leads_df["audit_score"].mean(), 1) if not leads_df.empty and "audit_score" in leads_df.columns else "N/A"

    col1, col2, col3, col4, col5, col6 = st.columns(6)
    col1.metric("Total Leads", f"{total_leads:,}")
    col2.metric("Qualified", f"{qualified:,}")
    col3.metric("Emails Sent", f"{emails_sent:,}")
    col4.metric("Active Queries", f"{active_queries:,}")
    col5.metric("Avg Audit Score", str(avg_audit_score))
    col6.metric("Campaigns", f"{total_campaigns:,}")

    st.divider()

    # Two charts side by side: Lead Funnel + Email Funnel
    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("🔍 Lead Pipeline")
        if not leads_df.empty and "status" in leads_df.columns:
            status_counts = leads_df["status"].value_counts()
            stages_map = {
                "pending_audit": "Discovered",
                "qualified": "Qualified",
                "unqualified": "Unqualified",
                "sent": "Emailed",
            }
            funnel_vals = [(stages_map.get(s, s), status_counts.get(s, 0)) for s in stages_map]
            fig_funnel = go.Figure(go.Funnel(
                y=[v[0] for v in funnel_vals],
                x=[v[1] for v in funnel_vals],
                textposition="inside",
                textinfo="value+percent initial",
                marker={"color": ["#636EFA", "#00CC96", "#EF553B", "#AB63FA"]},
            ))
            fig_funnel.update_layout(height=320, margin=dict(l=20, r=20, t=30, b=10))
            st.plotly_chart(fig_funnel, use_container_width=True)
        else:
            st.info("No lead data yet")

    with col_right:
        st.subheader("📧 Email Performance")
        if not camp_df.empty and "status" in camp_df.columns:
            sent_count = (camp_df["status"] == "sent").sum()
            opened_count = camp_df["opened_at"].notna().sum() if "opened_at" in camp_df.columns else 0
            clicked_count = camp_df["clicked_at"].notna().sum() if "clicked_at" in camp_df.columns else 0
            replied_count = camp_df["replied_at"].notna().sum() if "replied_at" in camp_df.columns else 0

            fig_email_funnel = go.Figure(go.Funnel(
                y=["Sent", "Opened", "Clicked", "Replied"],
                x=[sent_count, opened_count, clicked_count, replied_count],
                textposition="inside",
                textinfo="value+percent initial",
                marker={"color": ["#636EFA", "#00CC96", "#FFA15A", "#EF553B"]},
            ))
            fig_email_funnel.update_layout(height=320, margin=dict(l=20, r=20, t=30, b=10))
            st.plotly_chart(fig_email_funnel, use_container_width=True)
        else:
            st.info("No email data yet")

    # Lead status pie
    if not leads_df.empty and "status" in leads_df.columns:
        status_counts = leads_df["status"].value_counts()
        fig_pie = go.Figure(data=[go.Pie(
            labels=status_counts.index.tolist(),
            values=status_counts.values.tolist(),
            hole=0.4,
            marker_colors=["#636EFA", "#00CC96", "#EF553B", "#AB63FA", "#FFA15A"],
        )])
        fig_pie.update_layout(
            title="Lead Status Distribution",
            height=300,
            margin=dict(l=20, r=20, t=40, b=10),
        )
        fig_pie.update_traces(textposition="inside", textinfo="value+percent")
        st.plotly_chart(fig_pie, use_container_width=True)

# ===== LEADS TAB =====
with tab_leads:
    if leads_df.empty:
        st.info("No lead data available")
    else:
        col_a, col_b = st.columns(2)

        with col_a:
            st.subheader("📈 Audit Score Distribution")
            if "audit_score" in leads_df.columns:
                scores = leads_df["audit_score"].dropna()
                if not scores.empty:
                    fig_hist = go.Figure(data=[go.Histogram(
                        x=scores,
                        nbinsx=20,
                        marker_color="#00CC96",
                    )])
                    fig_hist.update_layout(
                        xaxis_title="Score",
                        yaxis_title="Leads",
                        height=300,
                        margin=dict(l=40, r=20, t=20, b=40),
                    )
                    st.plotly_chart(fig_hist, use_container_width=True)
                else:
                    st.info("No audit scores yet")
            else:
                st.info("No audit score data")

        with col_b:
            st.subheader("🖥️ Top Platforms")
            if "platform_detected" in leads_df.columns:
                platform_counts = leads_df["platform_detected"].value_counts().head(10)
                fig_platform = go.Figure(data=[go.Bar(
                    x=platform_counts.values.tolist(),
                    y=platform_counts.index.tolist(),
                    orientation="h",
                    marker_color="#AB63FA",
                )])
                fig_platform.update_layout(
                    xaxis_title="Count",
                    yaxis_title="Platform",
                    height=300,
                    margin=dict(l=40, r=20, t=20, b=40),
                )
                st.plotly_chart(fig_platform, use_container_width=True)
            else:
                st.info("No platform data")

        # Lead timeline
        st.subheader("📅 Leads Over Time")
        if "created_at" in leads_df.columns:
            valid_dates = leads_df["created_at"].dropna()
            if not valid_dates.empty:
                freq = st.selectbox("Aggregation", ["Daily", "Weekly", "Monthly"], index=0)
                freq_map = {"Daily": "D", "Weekly": "W", "Monthly": "ME"}
                period_freq = freq_map[freq]
                leads_df["_period"] = valid_dates.dt.to_period(period_freq).astype(str)
                timeline = leads_df.groupby("_period").size().reset_index(name="leads")
                fig_timeline = go.Figure(data=[go.Scatter(
                    x=timeline["_period"],
                    y=timeline["leads"],
                    mode="lines+markers",
                    line=dict(color="#636EFA", width=2),
                    marker=dict(size=6),
                )])
                fig_timeline.update_layout(
                    xaxis_title="Date",
                    yaxis_title="Leads Created",
                    height=300,
                    margin=dict(l=40, r=20, t=20, b=40),
                )
                st.plotly_chart(fig_timeline, use_container_width=True)
            else:
                st.info("No date data")
        else:
            st.info("No created_at column")

        # Location distribution
        st.subheader("📍 Top Locations")
        if "location" in leads_df.columns:
            loc_counts = leads_df["location"].value_counts().head(10)
            fig_loc = go.Figure(data=[go.Bar(
                x=loc_counts.values.tolist(),
                y=loc_counts.index.tolist(),
                orientation="h",
                marker_color="#FFA15A",
            )])
            fig_loc.update_layout(
                xaxis_title="Leads",
                yaxis_title="Location",
                height=300,
                margin=dict(l=40, r=20, t=20, b=40),
            )
            st.plotly_chart(fig_loc, use_container_width=True)

# ===== EMAIL CAMPAIGNS TAB =====
with tab_email:
    if camp_df.empty:
        st.info("No email campaign data. Generate and send emails first.")
    else:
        # Email gauges
        sent_total = (camp_df["status"] == "sent").sum() if "status" in camp_df.columns else 0
        opened_total = camp_df["opened_at"].notna().sum() if "opened_at" in camp_df.columns else 0
        clicked_total = camp_df["clicked_at"].notna().sum() if "clicked_at" in camp_df.columns else 0
        replied_total = camp_df["replied_at"].notna().sum() if "replied_at" in camp_df.columns else 0

        open_rate = (opened_total / sent_total * 100) if sent_total > 0 else 0
        click_rate = (clicked_total / sent_total * 100) if sent_total > 0 else 0
        reply_rate = (replied_total / sent_total * 100) if sent_total > 0 else 0

        st.subheader("📊 Email Rates")
        fig_gauges = make_subplots(rows=1, cols=3, subplot_titles=["Open Rate", "Click Rate", "Reply Rate"])

        fig_gauges.add_trace(go.Indicator(
            mode="gauge+number", value=open_rate,
            gauge={"axis": {"range": [0, 100]}, "bar": {"color": "#00CC96"},
                   "steps": [{"range": [0, 20], "color": "#EF553B"}, {"range": [20, 40], "color": "#FFA15A"}, {"range": [40, 100], "color": "#00CC96"}]},
            number={"suffix": "%"},
        ), row=1, col=1)

        fig_gauges.add_trace(go.Indicator(
            mode="gauge+number", value=click_rate,
            gauge={"axis": {"range": [0, 100]}, "bar": {"color": "#636EFA"},
                   "steps": [{"range": [0, 5], "color": "#EF553B"}, {"range": [5, 15], "color": "#FFA15A"}, {"range": [15, 100], "color": "#636EFA"}]},
            number={"suffix": "%"},
        ), row=1, col=2)

        fig_gauges.add_trace(go.Indicator(
            mode="gauge+number", value=reply_rate,
            gauge={"axis": {"range": [0, 50]}, "bar": {"color": "#AB63FA"},
                   "steps": [{"range": [0, 5], "color": "#EF553B"}, {"range": [5, 15], "color": "#FFA15A"}, {"range": [15, 50], "color": "#AB63FA"}]},
            number={"suffix": "%"},
        ), row=1, col=3)

        fig_gauges.update_layout(height=220, margin=dict(l=20, r=20, t=40, b=20))
        st.plotly_chart(fig_gauges, use_container_width=True)

        # Status distribution
        st.subheader("📋 Campaign Status")
        if "status" in camp_df.columns:
            status_counts = camp_df["status"].value_counts()
            fig_status = go.Figure(data=[go.Bar(
                x=status_counts.index.tolist(),
                y=status_counts.values.tolist(),
                marker_color=["#636EFA", "#00CC96", "#EF553B", "#AB63FA", "#FFA15A"][:len(status_counts)],
            )])
            fig_status.update_layout(height=280, margin=dict(l=40, r=20, t=20, b=40))
            st.plotly_chart(fig_status, use_container_width=True)

        # Engagement over time
        st.subheader("📈 Engagement Over Time")
        if "sent_at" in camp_df.columns:
            sent_dates = camp_df["sent_at"].dropna()
            if not sent_dates.empty:
                camp_df_copy = camp_df[["sent_at", "opened_at", "clicked_at", "replied_at"]].dropna(subset=["sent_at"]).copy()
                camp_df_copy["date"] = camp_df_copy["sent_at"].dt.to_period("D").astype(str)
                daily = camp_df_copy.groupby("date").agg(
                    sent=("sent_at", "count"),
                    opened=("opened_at", lambda x: x.notna().sum()),
                    clicked=("clicked_at", lambda x: x.notna().sum()),
                    replied=("replied_at", lambda x: x.notna().sum()),
                ).reset_index()

                fig_engagement = go.Figure()
                fig_engagement.add_trace(go.Bar(x=daily["date"], y=daily["sent"], name="Sent", marker_color="#636EFA"))
                fig_engagement.add_trace(go.Scatter(x=daily["date"], y=daily["opened"], name="Opened", line=dict(color="#00CC96", width=2), mode="lines+markers"))
                fig_engagement.add_trace(go.Scatter(x=daily["date"], y=daily["clicked"], name="Clicked", line=dict(color="#FFA15A", width=2), mode="lines+markers"))
                fig_engagement.add_trace(go.Scatter(x=daily["date"], y=daily["replied"], name="Replied", line=dict(color="#EF553B", width=2), mode="lines+markers"))
                fig_engagement.update_layout(
                    height=320,
                    hovermode="x unified",
                    legend=dict(orientation="h", yanchor="bottom", y=1.02),
                    margin=dict(l=40, r=20, t=20, b=40),
                )
                st.plotly_chart(fig_engagement, use_container_width=True)
            else:
                st.info("No sent date data")
        else:
            st.info("No sent_at column")

        # Data table (collapsed by default)
        with st.expander("📋 Raw Campaign Data"):
            display_cols = ["id", "status", "sent_at", "bounce_reason"]
            available = [c for c in display_cols if c in camp_df.columns]
            st.dataframe(camp_df[available], use_container_width=True, height=400)

# ===== QUERY PERFORMANCE TAB =====
with tab_queries:
    if query_df.empty:
        st.info("No query performance data. Run discovery first.")
    else:
        query_df["success_rate"] = (
            query_df["total_leads_saved"] / query_df["total_executions"].clip(lower=1) * 100
        ).round(1)

        # KPI row
        st.subheader("📈 Query Summary")
        col_q1, col_q2, col_q3, col_q4 = st.columns(4)
        col_q1.metric("Total Queries", f"{len(query_df):,}")
        col_q2.metric("Active", f"{query_df['is_active'].sum():,}")
        col_q3.metric("Inactive", f"{(~query_df['is_active']).sum():,}")
        col_q4.metric(
            "Avg Success Rate",
            f"{(query_df['total_leads_saved'].sum() / max(query_df['total_executions'].sum(), 1) * 100):.1f}%",
        )

        st.divider()

        # Top queries by leads saved
        st.subheader("🏆 Top Queries")
        top_n = st.slider("Show top N queries", 5, 30, 10)
        top_queries = query_df.nlargest(top_n, "total_leads_saved")

        fig_top = go.Figure(data=[go.Bar(
            y=top_queries["query_pattern"].tolist() if "query_pattern" in top_queries.columns else list(range(len(top_queries))),
            x=top_queries["total_leads_saved"].tolist(),
            orientation="h",
            marker_color=top_queries["success_rate"].tolist() if "success_rate" in top_queries.columns else None,
            text=top_queries["success_rate"].round(1).tolist() if "success_rate" in top_queries.columns else None,
            textposition="outside",
        )])
        fig_top.update_layout(
            xaxis_title="Leads Saved",
            yaxis={"categoryorder": "total ascending"},
            height=max(300, top_n * 35),
            margin=dict(l=40, r=60, t=20, b=40),
        )
        if "success_rate" in top_queries.columns:
            fig_top.update_layout(coloraxis_showscale=False)
        st.plotly_chart(fig_top, use_container_width=True)

        # Active vs Inactive pie
        col_pie1, col_pie2 = st.columns(2)
        with col_pie1:
            active_count = query_df["is_active"].sum() if "is_active" in query_df.columns else 0
            inactive_count = len(query_df) - active_count
            fig_pie = go.Figure(data=[go.Pie(
                labels=["Active", "Inactive"],
                values=[active_count, inactive_count],
                hole=0.4,
                marker_colors=["#00CC96", "#EF553B"],
            )])
            fig_pie.update_layout(title="Active vs Inactive Queries", height=280)
            fig_pie.update_traces(textposition="inside", textinfo="value+percent")
            st.plotly_chart(fig_pie, use_container_width=True)

        # Data table
        with col_pie2:
            st.subheader("📋 Query Details")
            display_cols = [
                "query_pattern", "city", "is_active",
                "total_executions", "total_leads_found", "total_leads_saved",
                "success_rate", "consecutive_failures",
            ]
            available_q = [c for c in display_cols if c in query_df.columns]
            st.dataframe(
                query_df[available_q].head(50),
                use_container_width=True,
                height=280,
            )
