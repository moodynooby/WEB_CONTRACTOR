"""Email Campaign Page - Generate, Review, and Send Emails."""

import streamlit as st
from core.db_repository import get_emails_for_review, delete_email, update_email_content
from core.logging import get_logger
from core.streamlit_utils import get_app

logger = get_logger(__name__)

st.set_page_config(page_title="Email", layout="wide")
st.title("Email Dashboard")


app = get_app()

st.session_state.setdefault("email_sending", set())
st.session_state.setdefault("email_gen_running", False)
st.session_state.setdefault("review_idx", 0)
st.session_state.setdefault("review_mode", False)

gen_limit = st.number_input("Max Leads", 1, 100, 20, 5)
if st.session_state.email_gen_running:
    st.warning("⏳ Generation in progress...")
if st.button("🔄 Reload", type="secondary"):
    st.rerun()

if st.button("Cancel", type="secondary"):
            st.session_state.email_gen_running = False
            st.rerun()
elif st.button("🚀 Generate", type="primary", use_container_width=True):
            st.session_state.email_gen_running = True
            with st.status("Generating emails...", expanded=True) as status:
                try:
                    result = app.generate_emails(
                        limit=gen_limit,
                        progress_callback=lambda c, t, m: status.update(label=f"{m} ({c}/{t})"),
                    )
                    status.update(
                        label=f"✅ {result.get('generated', 0)} emails generated",
                        state="complete",
                    )
                except Exception as e:
                    status.update(label=f"❌ Failed: {e}", state="error")
                    logger.error(f"Email generation error: {e}")
            st.session_state.email_gen_running = False
            st.rerun()

emails = get_emails_for_review()
logger.info(f"Fetched {len(emails)} emails for review")

if not emails:
    st.info("No emails pending review. Generate emails first.")
    st.stop()

for email in emails:
    email.setdefault("to_email", email.get("email", ""))
    logger.debug(f"Email: {email.get('business_name')} | status={email.get('status')}")

unreviewed = [e for e in emails if e.get("status") == "needs_review"]
reviewed = [e for e in emails if e.get("status") in ("sent", "approved", "rejected", "pending")]

logger.info(f"Unreviewed: {len(unreviewed)} | Reviewed: {len(reviewed)}")

# === REVIEW MODE ===
if st.session_state.review_mode and unreviewed:
    idx = st.session_state.review_idx
    if idx >= len(unreviewed):
        idx = 0
        st.session_state.review_idx = 0
    
    email = unreviewed[idx]
    status_emoji = {"needs_review": "🟡", "sent": "🟢", "approved": "✅", "rejected": "❌"}
    
    st.subheader(f"🔍 Review Mode ({idx + 1}/{len(unreviewed)})")
    st.progress((idx + 1) / len(unreviewed))
    
    col_header1, col_header2, col_header3 = st.columns([2, 2, 1])
    with col_header1:
        st.markdown(f"**Business:** {email.get('business_name', 'N/A')}")
    with col_header2:
        st.markdown(f"**To:** `{email.get('to_email', 'N/A')}`")
    with col_header3:
        if email.get("social_links"):
            with st.popover("🔗 Links"):
                for p, u in email["social_links"].items():
                    if u:
                        st.markdown(f"[{p}]({u})")
    
    subject_key = f"review_subj_{email.get('id', idx)}"
    body_key = f"review_body_{email.get('id', idx)}"
    
    subject = st.text_input("Subject", email.get("subject", ""), key=subject_key)
    body = st.text_area("Body", email.get("body", ""), height=300, key=body_key)
    
    st.divider()
    col_actions = st.columns([1, 1, 1, 1, 2])
    
    with col_actions[0]:
        if st.button("✅ Approve & Send", type="primary", use_container_width=True):
            try:
                update_email_content(email.get("id"), subject, body)
                success = app.send_email(
                    to_email=email["to_email"],
                    subject=subject,
                    body=body,
                    campaign_id=email.get("id"),
                )
                if success:
                    st.success("✅ Approved & sent!")
                    st.session_state.review_idx = idx + 1
                    st.rerun()
            except Exception as e:
                st.error(f"Failed: {e}")
    
    with col_actions[1]:
        if st.button("❌ Reject", type="secondary", use_container_width=True):
            delete_email(email.get("id"))
            st.success("❌ Rejected & deleted")
            st.session_state.review_idx = min(idx, len(unreviewed) - 2)
            st.rerun()
    
    with col_actions[2]:
        if st.button("⏭️ Skip", use_container_width=True):
            st.session_state.review_idx = idx + 1
            st.rerun()
    
    with col_actions[3]:
        if st.button("⏮️ Previous", use_container_width=True, disabled=idx == 0):
            st.session_state.review_idx = idx - 1
            st.rerun()
    
    with col_actions[4]:
        st.caption(f"Duration: {email.get('duration', 0):.2f}s | Status: `{email.get('status', 'unknown')}`")
    
    st.divider()
    if st.button("🔙 Exit Review Mode"):
        st.session_state.review_mode = False
        st.session_state.review_idx = 0
        st.rerun()

else:
    if st.session_state.review_mode and not unreviewed:
        st.success("🎉 All emails reviewed!")
        st.session_state.review_mode = False
    
    st.subheader(f"📬 Emails ({len(unreviewed)} unreviewed, {len(reviewed)} reviewed)")
    
    if unreviewed and not st.session_state.review_mode:
        if st.button("🔍 Start Review Mode", type="primary", use_container_width=True):
            st.session_state.review_mode = True
            st.session_state.review_idx = 0
            st.rerun()
    
    if reviewed:
        st.caption("REVIEWED")
        for email in reviewed:
            status = email.get("status", "unknown")
            emoji = status_emoji.get(status, "⚪")
            with st.expander(f"{emoji} {email.get('business_name', 'Unknown')} — {email.get('to_email', 'N/A')} ({status})"):
                st.markdown(f"**Subject:** {email.get('subject', 'N/A')}")
                st.text_area("Body", email.get("body", ""), height=150, key=f"old_body_{email.get('id')}")
                st.caption(f"Duration: {email.get('duration', 0):.2f}s")
