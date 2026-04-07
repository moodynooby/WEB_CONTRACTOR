"""Generates personalized cold emails for qualified leads."""

import json
import time
from typing import Callable

from infra import llm
from infra.settings import (
    DEFAULT_MODEL,
    EMAIL_MAX_RETRIES,
    load_json_section,
)
from infra.logging import get_logger
from database.repository import (
    get_qualified_leads,
    save_emails_batch,
    update_lead_status,
)
from outreach.discovery import scrape_email_from_website


class EmailGenerator:
    """Generates personalized cold emails for qualified leads."""

    def __init__(self) -> None:
        self.logger = get_logger(self.__class__.__name__)
        self.email_config = load_json_section("email_generation")
        self.llm_config = load_json_section("llm")

    def log(self, message: str, style: str = "") -> None:
        """Log message with level awareness."""
        if style == "error":
            self.logger.error(message)
        elif style == "warning":
            self.logger.warning(message)
        elif style == "success":
            self.logger.info(message)
        else:
            self.logger.debug(message)

    def generate(
        self, limit: int = 20, progress_callback: Callable | None = None
    ) -> dict:
        """Generate emails for qualified leads."""
        self.log("\n=== EMAIL GENERATION ===", "info")

        leads = get_qualified_leads(limit)
        self.log(f"Found {len(leads)} qualified leads", "info")

        if not leads:
            return {"generated": 0}

        generated = 0
        email_batch = []

        for i, lead in enumerate(leads, 1):
            lead_email = (lead.get("email") or "").strip()
            if not lead_email:
                self.log(
                    f"  [{i}/{len(leads)}] {lead['business_name']} - "
                    "No email, attempting to scrape...",
                    "info",
                )
                website = lead.get("website", "")
                if website:
                    lead_email = scrape_email_from_website(website)
                    if lead_email:
                        self.log(
                            f"  [{i}/{len(leads)}] {lead['business_name']} - "
                            f"Found email: {lead_email}",
                            "success",
                        )
                    else:
                        self.log(
                            f"  [{i}/{len(leads)}] {lead['business_name']} - "
                            "No email found, skipping",
                            "warning",
                        )
                        update_lead_status(lead["id"], "unqualified")
                        continue
                else:
                    self.log(
                        f"  [{i}/{len(leads)}] {lead['business_name']} - "
                        "No website, skipping",
                        "warning",
                    )
                    update_lead_status(lead["id"], "unqualified")
                    continue

            self.log(f"  [{i}/{len(leads)}] {lead['business_name']}", "info")

            issues = lead.get("issues_json", [])
            if not isinstance(issues, list):
                try:
                    issues = json.loads(issues)
                except (json.JSONDecodeError, TypeError):
                    issues = []

            critical_issues = [i for i in issues if i.get("severity") == "critical"]
            warning_issues = [i for i in issues if i.get("severity") == "warning"]
            top_issues = (critical_issues + warning_issues)[:3]
            issues_text = "\n".join([f"- {i['description']}" for i in top_issues])

            bucket_templates = self.email_config.get("bucket_templates", {})
            bucket_template = bucket_templates.get(lead.get("bucket", "default"), {})
            angle = bucket_template.get("angle", "")
            cta = bucket_template.get("cta", "")

            prompt = self.email_config.get("prompt_template", "").format(
                business_name=lead["business_name"],
                bucket=lead.get("bucket", "default"),
                url=lead["website"],
                issue_summary=issues_text,
            )

            if angle:
                prompt += f"\n\nAngle: {angle}"
            if cta:
                prompt += f"\nCTA: {cta}"

            system_message = self.email_config.get("system_message", "")

            email_start = time.time()
            try:
                raw = llm.generate_with_retry(
                    model=DEFAULT_MODEL,
                    prompt=prompt,
                    system=system_message,
                    format_json=True,
                    max_retries=EMAIL_MAX_RETRIES,
                    timeout=self.email_config.get("timeout", 30),
                )
                data = json.loads(raw)

                subject = (data.get("subject") or "").strip()
                body = (data.get("body") or "").strip()

                if not subject or not body:
                    self.log("  ⚠ LLM returned empty email, retrying...", "warning")
                    raise ValueError("Empty subject or body")

                if len(body) < 20:
                    self.log("  ⚠ Email too short, retrying...", "warning")
                    raise ValueError("Email too short")

                email_data = {
                    "lead_id": lead["id"],
                    "to_email": lead_email,
                    "subject": subject,
                    "body": body,
                    "status": "needs_review",
                    "variation": "default",
                    "duration": time.time() - email_start,
                }
                email_batch.append(email_data)
                generated += 1

            except Exception as e:
                self.log(f"  ⚠ Email generation failed: {e}", "error")

            if progress_callback:
                progress_callback(
                    i, len(leads), f"Generating for {lead['business_name']}"
                )

        if email_batch:
            save_emails_batch(email_batch)
            self.log(f"  Saved {len(email_batch)} emails", "success")

        self.log(f"Email Generation Complete: {generated} emails generated", "success")

        return {"generated": generated}

    def refine(
        self,
        subject: str,
        body: str,
        instructions: str,
    ) -> dict[str, str]:
        """Refine an existing email based on user instructions using LLM."""
        llm_settings = self.llm_config

        if not self.email_config.get("enabled", True):
            self.log("Email refinement disabled", "warning")
            return {"subject": subject, "body": body}

        prompt = f"""Refine this cold email based on instructions.

Instructions: {instructions}

Current Subject: {subject}
Current Body:
{body}

Return ONLY JSON: {{"subject": "refined subject line", "body": "refined email body"}}"""

        try:
            raw = llm.generate_with_retry(
                model=llm_settings.get("default_model", "llama-3.1-8b-instant"),
                prompt=prompt,
                system="You are a professional email editor. Output ONLY valid JSON.",
                format_json=True,
                max_retries=llm_settings.get("max_retries", 2),
                timeout=llm_settings.get("timeout_seconds", 30),
            )
            data = json.loads(raw)
            return {
                "subject": data.get("subject", subject),
                "body": data.get("body", body),
            }
        except llm.ProviderError as e:
            self.log(f"Email refinement failed: {e}", "error")
            return {"subject": subject, "body": body}
