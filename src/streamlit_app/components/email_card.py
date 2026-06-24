"""Email card component for Streamlit.

Renders a single email with editable subject/body and action buttons.
"""

import streamlit as st
from services.email_service import EmailService
from streamlit_app.components.log_viewer import append_log


def show_email_card(email: dict, email_service: EmailService) -> bool:
    """Display a single email card with editable fields and action buttons.

    Args:
        email: Email dict from get_emails_for_review().
        email_service: EmailService instance for operations.

    Returns:
        True if the email was deleted (caller should rerun), False otherwise.
    """
    cid = email["id"]

    with st.container():
        st.markdown(
            f"""
            <div style="
                background-color: #1e1e1e;
                border: 1px solid #333;
                border-radius: 8px;
                padding: 16px;
                margin-bottom: 12px;
            ">
                <h4 style="margin:0; color:#fcfcfc;">{email.get('business_name', 'Unknown')}</h4>
                <p style="margin:4px 0; color:#aaa; font-size:12px;">
                    To: {email.get('to_email', '')} | Status: {email.get('status', 'needs_review')}
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        col1, col2 = st.columns([3, 1])

        with col1:
            subject = st.text_input(
                "Subject",
                value=email.get("subject", ""),
                key=f"subj_{cid}",
                label_visibility="collapsed",
                placeholder="Subject",
            )
            body = st.text_area(
                "Body",
                value=email.get("body", ""),
                key=f"body_{cid}",
                height=200,
                label_visibility="collapsed",
                placeholder="Email body...",
            )

            links = []
            social = email.get("social_links", {}) or {}
            if isinstance(social, dict):
                for key, url in social.items():
                    if url:
                        links.append(f"{key}: {url}")
            contact = email.get("contact_form_url")
            if contact:
                links.append(f"Contact Form: {contact}")
            if links:
                st.caption(" | ".join(links))

        with col2:
            if f"card_disabled_{cid}" not in st.session_state:
                st.session_state[f"card_disabled_{cid}"] = False
            card_disabled = st.session_state[f"card_disabled_{cid}"]

            if st.button("Approve", key=f"app_{cid}", disabled=card_disabled, use_container_width=True):
                try:
                    email_service.approve(cid, subject, body)
                    st.session_state[f"card_disabled_{cid}"] = True
                    append_log(f"Approved email for {email.get('business_name', '')}")
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))

            if st.button("Delete", key=f"del_{cid}", disabled=card_disabled, use_container_width=True):
                st.session_state.confirmed_delete_email = cid
                st.rerun()

            if st.button("Refine", key=f"ref_{cid}", disabled=card_disabled, use_container_width=True):
                instructions = st.session_state.get(f"refine_instr_{cid}", "")
                if instructions:
                    try:
                        result = email_service.refine(cid, instructions, subject, body)
                        st.session_state[f"subj_{cid}"] = result["subject"]
                        st.session_state[f"body_{cid}"] = result["body"]
                        st.session_state[f"refine_instr_{cid}"] = ""
                        append_log(f"Refined email for {email.get('business_name', '')}")
                        st.rerun()
                    except ValueError as e:
                        st.error(str(e))
                else:
                    st.toast("Enter refine instructions in the text area below", icon="ℹ️")

            st.text_area(
                "Refine instructions",
                key=f"refine_instr_{cid}",
                height=68,
                label_visibility="collapsed",
                placeholder="e.g. Make it shorter",
            )

            if st.button("Regenerate", key=f"reg_{cid}", disabled=card_disabled, use_container_width=True):
                try:
                    result = email_service.regenerate(cid, email.get("lead_id", ""))
                    st.session_state[f"subj_{cid}"] = result["subject"]
                    st.session_state[f"body_{cid}"] = result["body"]
                    append_log(f"Regenerated email for {email.get('business_name', '')}")
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))

            if st.button("Send", key=f"snd_{cid}", disabled=card_disabled, use_container_width=True):
                try:
                    success = email_service.send(
                        cid,
                        email.get("to_email", ""),
                        subject,
                        body,
                        email.get("lead_id"),
                    )
                    if success:
                        st.session_state[f"card_disabled_{cid}"] = True
                        append_log(f"Sent email to {email.get('to_email', '')}")
                        st.rerun()
                    else:
                        st.error("Send failed. Check logs.")
                except ValueError as e:
                    st.error(str(e))

        st.divider()

    return False
