"""Audit Page - Lead Audit Pipeline."""

import streamlit as st
from database.repository import count_leads, get_pending_audits, get_qualified_leads
from infra.logging import get_logger
from ui.utils import get_app

logger = get_logger(__name__)

st.set_page_config(page_title="Audit", layout="wide")

st.title("📋 Lead Audit")
st.caption("Audit pending leads using multi-agent pipeline")

app = get_app()

if "audit_running" not in st.session_state:
    st.session_state.audit_running = False
if "audit_result" not in st.session_state:
    st.session_state.audit_result = None

# --- Sidebar ---
pending_count = len(get_pending_audits(limit=1))
qualified_count = len(get_qualified_leads(limit=1))
total_leads = count_leads()

with st.sidebar:
    st.subheader("📊 Quick Stats")
    st.metric("Total Leads", f"{total_leads:,}")
    st.metric("Pending Audit", f"{pending_count:,}")
    st.metric("Qualified", f"{qualified_count:,}")

    st.divider()

    st.subheader("⚡ Quick Actions")
    if st.session_state.audit_running:
        st.warning("⏳ Audit in progress...")
        if st.button("⏹️ Cancel Audit", type="secondary", use_container_width=True):
            st.session_state.audit_running = False
            st.rerun()
    elif st.button("🔍 Run Audit", type="primary", use_container_width=True):
        st.session_state.audit_running = True
        st.session_state.audit_result = None
        st.rerun()

col1, col2 = st.columns(2)
with col1:
    limit = st.number_input(
        "Max Leads to Audit",
        min_value=1,
        max_value=100,
        value=20,
        step=5,
    )


if st.session_state.audit_running:
    st.warning("⏳ Audit already in progress...")
    if st.button("Cancel", type="secondary"):
        st.session_state.audit_running = False
        st.rerun()
elif st.button("🔍 Run Audit", type="primary", disabled=st.session_state.audit_running):
    st.session_state.audit_running = True
    st.session_state.audit_result = None

    with st.status("Running audit...", expanded=True) as status:

        def progress_callback(current: int, total: int, message: str):
            status.update(label=f"Auditing lead {current}/{total}")

        try:
            result = app.run_audit(
                limit=limit,
                progress_callback=progress_callback,
            )
            st.session_state.audit_result = result
            status.update(
                label="✅ Audit complete!",
                state="complete",
                expanded=False,
            )
        except Exception as e:
            st.session_state.audit_result = {"error": str(e)}
            status.update(
                label=f"❌ Audit failed: {e}",
                state="error",
                expanded=True,
            )
            logger.error(f"Audit error: {e}")

    st.session_state.audit_running = False

    if st.session_state.audit_result and "error" not in st.session_state.audit_result:
        result = st.session_state.audit_result
        col1, col2, col3 = st.columns(3)
        col1.metric("Leads Audited", result["audited"])
        col2.metric("Leads Qualified", result["qualified"])

        audited = int(result.get("audited", 0))
        qualified = int(result.get("qualified", 0))
        if audited > 0:
            qual_rate = (qualified / audited) * 100
            col3.metric("Qualification Rate", f"{qual_rate:.1f}%")
    elif st.session_state.audit_result and "error" in st.session_state.audit_result:
        st.error(f"Audit failed: {st.session_state.audit_result['error']}")

with st.expander("ℹ️ About Audit"):
    st.markdown(
        """
    Multi-agent audit pipeline:
    1. **Content Agent**: Analyzes copy quality and CTAs (LLM-based)
    2. **Business Agent**: Industry-specific checks (LLM-based)
    3. **Technical Agent**: SEO, meta tags, structured data (rule-based)
    4. **Performance Agent**: Page speed indicators (rule-based)

    Agents run in parallel. Scores are weighted and aggregated.
    Leads qualify if score < threshold (website needs improvement = good lead).
    """
    )
