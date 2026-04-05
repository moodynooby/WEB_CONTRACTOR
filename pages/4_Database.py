"""Database Page - Browse and Filter Leads."""

import streamlit as st
import pandas as pd
from core.db_models import Lead
from core import db
from core.logging import get_logger

logger = get_logger(__name__)

st.title("💾 Database Browser")
st.caption("Browse and filter all leads in the database")

with db:
    leads = Lead.select().dicts()
    leads_df = pd.DataFrame(leads)

if leads_df.empty:
    st.info("No leads in database. Run discovery first.")
else:
    col1, col2, col3 = st.columns(3)
    
    with col1:
        status_filter = st.multiselect(
            "Status",
            options=leads_df["status"].unique().tolist(),
            default=leads_df["status"].unique().tolist(),
        )
    
    with col2:
        bucket_filter = st.multiselect(
            "Bucket",
            options=sorted(leads_df.get("bucket_id", pd.Series()).dropna().unique().tolist()) if "bucket_id" in leads_df.columns else [],
            default=[],
        )
    
    with col3:
        search = st.text_input("Search")

    filtered = leads_df[leads_df["status"].isin(status_filter)]
    
    if search:
        mask = filtered["business_name"].str.contains(search, case=False, na=False) | \
               filtered["website"].str.contains(search, case=False, na=False)
        filtered = filtered[mask]

    st.write(f"**{len(filtered)}** leads shown (out of {len(leads_df)} total)")

    st.dataframe(
        filtered[[
            "business_name",
            "website",
            "email",
            "location",
            "status",
            "audit_score",
            "created_at",
        ]],
        use_container_width=True,
        height=600,
    )

    st.subheader("📊 Statistics")
    col1, col2, col3, col4 = st.columns(4)
    
    col1.metric("Total Leads", len(leads_df))
    col2.metric("Pending Audit", len(leads_df[leads_df["status"] == "pending_audit"]))
    col3.metric("Qualified", len(leads_df[leads_df["status"] == "qualified"]))
    col4.metric("Emails Sent", len(leads_df[leads_df["status"] == "sent"]))
