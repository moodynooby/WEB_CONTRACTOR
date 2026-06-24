"""Generates personalized cold emails for qualified leads."""

import json
import time
from typing import Callable

from infra import llm
from infra.settings import (
    DEFAULT_MODEL,
    EMAIL_MAX_RETRIES,
    get_section,
)
from infra.logging import get_logger
from database.lead_repo import get_qualified_leads, update_lead_status
from database.email_repo import save_emails_batch
from outreach.discovery import scrape_email_from_website


class EmailGenerator:
    """Generates personalized cold emails for qualified leads."""

    def __init__(self) -> None:
        self.logger = get_logger(__name__)
        self.email_config = get_section("email_generation")
        self.llm_config = get_section("llm")

    def generate(
        self, limit: int = 20, progress_callback: Callable | None = None
    ) -> dict:
        """Generate emails for qualified leads."""
        self.logger.info("\n=== EMAIL GENERATION ===")

        leads = get_qualified_leads(limit)
        self.logger.info(f"Found {len(leads)} qualified leads")

        if not leads:
            return {"generated": 0}

        generated = 0
        email_batch = []

        for i, lead in enumerate(leads, 1):
            lead_email = (lead.get("email") or "").strip()
            if not lead_email:
                self.logger.info(
                    f"  [{i}/{len(leads)}] {lead['business_name']} - "
                    "No email, attempting to scrape...",
                )
                website = lead.get("website", "")
                if website:
                    lead_email = scrape_email_from_website(website)
                    if lead_email:
                        self.logger.info(
                            f"  [{i}/{len(leads)}] {lead['business_name']} - "
                            f"Found email: {lead_email}",
                        )
                    else:
                        self.logger.warning(
                            f"  [{i}/{len(leads)}] {lead['business_name']} - "
                            "No email found, skipping",
                        )
                        update_lead_status(lead["id"], "unqualified")
                        continue
                else:
                    self.logger.warning(
                        f"  [{i}/{len(leads)}] {lead['business_name']} - "
                        "No website, skipping",
                    )
                    update_lead_status(lead["id"], "unqualified")
                    continue

            self.logger.info(f"  [{i}/{len(leads)}] {lead['business_name']}")

            issues = lead.get("issues_json", [])
            if not isinstance(issues, list):
                try:
                    issues = json.loads(issues)
                except (json.JSONDecodeError, TypeError):
                    issues = []

            bucket_templates = self.email_config.get("bucket_templates", {})
            bucket_template = bucket_templates.get(lead.get("bucket", "default"), {})
            angle = bucket_template.get("angle", "")
            cta = bucket_template.get("cta", "")

            from outreach.prompts import (
                format_issues,
                build_email_prompt,
                get_email_system_message,
            )

            issues_text = format_issues(issues)
            prompt = build_email_prompt(
                business_name=lead["business_name"],
                bucket=lead.get("bucket", "default"),
                issues_summary=issues_text,
                url=lead["website"],
                angle=angle,
                cta=cta,
            )
            system_message = get_email_system_message()

            email_start = time.time()
            try:
                raw = llm.generate(
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
                    self.logger.warning("  ⚠ LLM returned empty email, retrying...")
                    raise ValueError("Empty subject or body")

                if len(body) < 20:
                    self.logger.warning("  ⚠ Email too short, retrying...")
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
                self.logger.error(f"  ⚠ Email generation failed: {e}")

            if progress_callback:
                progress_callback(
                    i, len(leads), f"Generating for {lead['business_name']}"
                )

        if email_batch:
            save_emails_batch(email_batch)
            self.logger.info(f"  Saved {len(email_batch)} emails")

        self.logger.info(f"Email Generation Complete: {generated} emails generated")

        return {"generated": generated}

    def generate_for_lead(self, lead: dict) -> dict[str, str]:
        """Generate a cold email for a single lead using the LLM.

        Args:
            lead: Dict with business_name, website, bucket, issues_json.

        Returns:
            Dict with 'subject' and 'body' keys.

        Raises:
            ValueError: If LLM returns empty or invalid response.
        """
        issues = lead.get("issues_json", [])
        if isinstance(issues, str):
            try:
                issues = json.loads(issues)
            except (json.JSONDecodeError, TypeError):
                issues = []

        bucket_templates = self.email_config.get("bucket_templates", {})
        bucket = lead.get("bucket", "default")
        bucket_template = bucket_templates.get(bucket, {})
        angle = bucket_template.get("angle", "")
        cta = bucket_template.get("cta", "")

        from outreach.prompts import (
            format_issues,
            build_email_prompt,
            get_email_system_message,
        )

        issues_text = format_issues(issues)
        prompt = build_email_prompt(
            business_name=lead.get("business_name", ""),
            bucket=bucket,
            issues_summary=issues_text,
            url=lead.get("website", ""),
            angle=angle,
            cta=cta,
        )
        system_message = get_email_system_message()

        raw = llm.generate(
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
            raise ValueError("LLM returned empty email")
        if len(body) < 20:
            raise ValueError("Email too short")

        return {"subject": subject, "body": body}

    def refine(
        self,
        subject: str,
        body: str,
        instructions: str,
    ) -> dict[str, str]:
        """Refine an existing email based on user instructions using LLM."""
        llm_settings = self.llm_config

        if not self.email_config.get("enabled", True):
            self.logger.warning("Email refinement disabled")
            return {"subject": subject, "body": body}

        from outreach.prompts import build_refine_prompt

        prompt = build_refine_prompt(subject, body, instructions)

        try:
            raw = llm.generate(
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
            self.logger.error(f"Email refinement failed: {e}")
            return {"subject": subject, "body": body}
