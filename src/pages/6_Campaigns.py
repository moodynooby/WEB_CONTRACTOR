"""Campaigns Page - Email Campaign Analytics."""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from database.repository import get_email_campaigns
from infra.logging import get_logger

logger = get_logger(__name__)

st.set_page_config(layout="wide")

st.title("📧 Email Campaign Analytics")
st.caption("Track email campaign performance and engagement metrics")

campaigns = get_email_campaigns()
campaigns_df = pd.DataFrame(campaigns)

if campaigns_df.empty:
    st.info("No email campaigns yet. Generate and send emails first.")
else:
    if "sent_at" in campaigns_df.columns:
        campaigns_df["sent_at"] = pd.to_datetime(
            campaigns_df["sent_at"], errors="coerce"
        )
    if "opened_at" in campaigns_df.columns:
        campaigns_df["opened_at"] = pd.to_datetime(
            campaigns_df["opened_at"], errors="coerce"
        )
    if "clicked_at" in campaigns_df.columns:
        campaigns_df["clicked_at"] = pd.to_datetime(
            campaigns_df["clicked_at"], errors="coerce"
        )
    if "replied_at" in campaigns_df.columns:
        campaigns_df["replied_at"] = pd.to_datetime(
            campaigns_df["replied_at"], errors="coerce"
        )

    total = len(campaigns_df)
    sent = (
        campaigns_df["status"].eq("sent").sum()
        if "status" in campaigns_df.columns
        else 0
    )
    pending = (
        campaigns_df["status"].eq("pending").sum()
        if "status" in campaigns_df.columns
        else 0
    )
    needs_review = (
        campaigns_df["status"].eq("needs_review").sum()
        if "status" in campaigns_df.columns
        else 0
    )
    approved = (
        campaigns_df["status"].eq("approved").sum()
        if "status" in campaigns_df.columns
        else 0
    )
    failed = (
        campaigns_df["status"].isin(["failed", "permanently_failed"]).sum()
        if "status" in campaigns_df.columns
        else 0
    )
    opened = (
        campaigns_df["opened_at"].notna().sum()
        if "opened_at" in campaigns_df.columns
        else 0
    )
    clicked = (
        campaigns_df["clicked_at"].notna().sum()
        if "clicked_at" in campaigns_df.columns
        else 0
    )
    replied = (
        campaigns_df["replied_at"].notna().sum()
        if "replied_at" in campaigns_df.columns
        else 0
    )
    bounced = (
        campaigns_df["bounce_reason"].notna().sum()
        if "bounce_reason" in campaigns_df.columns
        else 0
    )

    open_rate = (opened / sent * 100) if sent > 0 else 0
    click_rate = (clicked / sent * 100) if sent > 0 else 0
    reply_rate = (replied / sent * 100) if sent > 0 else 0
    bounce_rate = (bounced / sent * 100) if sent > 0 else 0

    st.subheader("📊 Campaign Overview")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Campaigns", f"{total:,}")
    col2.metric("Sent", f"{sent:,}")
    col3.metric("Pending Review", f"{needs_review:,}")
    col4.metric("Failed", f"{failed:,}")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Open Rate", f"{open_rate:.1f}%")
    col2.metric("Click Rate", f"{click_rate:.1f}%")
    col3.metric("Reply Rate", f"{reply_rate:.1f}%")
    col4.metric("Bounce Rate", f"{bounce_rate:.1f}%")

    tab1, tab2 = st.tabs(["📈 Performance", "📋 Details"])

    with tab1:
        col1, col2 = st.columns(2)
        with col1:
            if "status" in campaigns_df.columns:
                status_counts = campaigns_df["status"].value_counts()
                fig = go.Figure(
                    data=[
                        go.Bar(
                            x=status_counts.index.tolist(),
                            y=status_counts.values.tolist(),
                        )
                    ]
                )
                fig.update_layout(title="Campaigns by Status", height=350)
                st.plotly_chart(fig, use_container_width=True)

        with col2:
            engagement_data = {
                "Metric": ["Sent", "Opened", "Clicked", "Replied"],
                "Count": [sent, opened, clicked, replied],
            }
            fig = go.Figure(
                data=[
                    go.Bar(
                        x=engagement_data["Metric"],
                        y=engagement_data["Count"],
                    )
                ]
            )
            fig.update_layout(title="Engagement Funnel", height=350)
            st.plotly_chart(fig, use_container_width=True)

    with tab2:
        if "status" in campaigns_df.columns:
            status_filter = st.multiselect(
                "Filter by Status",
                options=campaigns_df["status"].unique().tolist(),
                default=campaigns_df["status"].unique().tolist(),
            )
            filtered_campaigns = campaigns_df[
                campaigns_df["status"].isin(status_filter)
            ]
        else:
            filtered_campaigns = campaigns_df

        st.write(f"**{len(filtered_campaigns):,}** campaigns shown")

        display_cols = ["id", "status", "sent_at", "bounce_reason"]
        display_df = filtered_campaigns[
            [c for c in display_cols if c in filtered_campaigns.columns]
        ].copy()
        st.dataframe(display_df, use_container_width=True, height=500)
