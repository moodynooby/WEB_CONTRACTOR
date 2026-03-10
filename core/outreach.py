"""Outreach Module: Lead Auditing + Email Generation (Stage B + Stage C)

Efficient resource management with per-operation browser contexts:
- Fresh browser context created for each audit operation
- LRU caching for email generation
- HTTP session reuse
- Proper Playwright lifecycle management
"""

import json
import re
import time
from contextlib import contextmanager
from functools import lru_cache
from typing import Any, Callable

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

from core import llm
from core.contact_finder import ContactFinder
from core.utils import load_json_config
from core.db_repository import (
    get_pending_audits,
    get_qualified_leads,
    save_audits_batch,
    save_emails_batch,
    update_lead_contact_info,
)


class Outreach:
    """Consolidated Stage B (Auditing) + Stage C (Email Generation) - Single-threaded"""

    def __init__(self, logger: Callable | None = None) -> None:
        self.logger = logger
        self.audit_settings = load_json_config("audit_settings.json")
        self.ollama_enabled = llm.is_available()
        self._llm_settings = load_json_config("app_settings.json").get(
            "llm_settings", {}
        )
        self.contact_finder = ContactFinder(logger=logger)

    def log(self, message: str, style: str = "") -> None:
        """Log message to provided logger or print."""
        if self.logger:
            self.logger(message, style)
        else:
            print(message)

    @contextmanager
    def managed_session(self):
        """Context manager for audit session - creates fresh browser context per operation."""
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            self._context = context

            try:
                yield self
            finally:
                context.close()
                browser.close()
                self._context = None

    def _get_playwright_page(self) -> Any:
        """Get new Playwright page from current context."""
        if not hasattr(self, "_context") or self._context is None:
            raise RuntimeError("Outreach must be used within managed_session()")
        return self._context.new_page()

    def _take_screenshot(self, url: str) -> str | None:
        """Capture website screenshot and return as base64 string."""
        try:
            page = self._get_playwright_page()
            page.goto(url, wait_until="networkidle", timeout=30000)
            screenshot_bytes = page.screenshot(type="png")
            import base64

            result = base64.b64encode(screenshot_bytes).decode("utf-8")
            page.close()
            return result
        except Exception as e:
            self.log(f"Failed to take screenshot: {e}", "error")
            return None

    def _run_visual_audit(
        self, business_name: str, base64_image: str, config: dict
    ) -> dict[str, Any] | None:
        """Run visual audit using Ollama Vision model."""
        prompt = config.get("prompt_template", "").format(business_name=business_name)
        system_message = config.get(
            "system_message",
            "You are an expert web design and UX auditor. Output ONLY valid JSON.",
        )

        try:
            raw = llm.generate(
                model=config.get("model", "richardyoung/smolvlm2-2.2b-instruct"),
                prompt=prompt,
                system=system_message,
                format_json=True,
                timeout=60,
            )
            return json.loads(raw)
        except llm.OllamaError as e:
            self.log(f"Visual audit failed: {e}", "error")
            return None

    def _normalize_severity(self, severity: str) -> str:
        """Normalize severity to match DB constraints."""
        mapping = {
            "critical": ["critical", "high", "error", "fatal"],
            "warning": ["warning", "medium", "warn"],
        }
        s = str(severity).lower().strip()
        for normalized, values in mapping.items():
            if s in values:
                return normalized
        return "info"

    def _query_selector(self, soup: BeautifulSoup, selector: str) -> str | None:
        """Query a single CSS selector from parsed BeautifulSoup object."""
        elem = soup.select_one(selector)
        return elem.get_text().strip() if elem else None

    def _query_selector_all(self, soup: BeautifulSoup, selector: str) -> list[str]:
        """Query all CSS selector matches from parsed BeautifulSoup object."""
        return [elem.get_text().strip() for elem in soup.select(selector)]

    def _strip_tags(self, html: str) -> str:
        """Remove all script and style tags, then get text content."""
        soup = BeautifulSoup(html, "html.parser")
        for elem in soup(["script", "style"]):
            elem.decompose()
        return soup.get_text(separator=" ", strip=True)

    def audit_website(
        self,
        url: str,
        business_name: str = "this business",
        bucket_name: str | None = None,
    ) -> dict:
        """Audit website for technical and qualitative issues + contact discovery."""
        issues: list[dict[str, Any]] = []
        score = 100

        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            response = llm.get_session().get(url, headers=headers, timeout=10)
            html_content = response.text
            soup = BeautifulSoup(html_content, "html.parser")

            discovered_info = self.contact_finder.discover_contact_info(html_content, url)

            if not discovered_info["email"] and discovered_info["contact_form_url"]:
                try:
                    c_resp = llm.get_session().get(
                        discovered_info["contact_form_url"], headers=headers, timeout=5
                    )
                    c_html = c_resp.text
                    c_info = self.contact_finder.discover_contact_info(
                        c_html, discovered_info["contact_form_url"]
                    )
                    if c_info["email"]:
                        discovered_info["email"] = c_info["email"]
                    if c_info["phone"] and not discovered_info["phone"]:
                        discovered_info["phone"] = c_info["phone"]
                except requests.RequestException as e:
                    self.log(
                        f"Error fetching contact page: {e}",
                        "error",
                    )
                except Exception as e:
                    self.log(f"Error parsing contact page: {e}", "error")

            checks = self.audit_settings.get("technical_checks", []).copy()
            if bucket_name and bucket_name in self.audit_settings.get(
                "bucket_overrides", {}
            ):
                overrides = self.audit_settings["bucket_overrides"][bucket_name]
                checks.extend(overrides.get("technical_checks", []))

            for check in checks:
                check_type = check.get("type")
                selector = check.get("selector")
                severity = self._normalize_severity(check.get("severity", "info"))

                if check_type == "html_exists":
                    elem = self._query_selector(soup, selector)
                    if not elem or (
                        check.get("min_length") and len(elem) < check["min_length"]
                    ):
                        issues.append(
                            {
                                "type": check["id"],
                                "severity": severity,
                                "description": check["description"],
                            }
                        )
                        score -= check["score_impact"]

                elif check_type == "html_count":
                    count = len(self._query_selector_all(soup, selector))
                    if check.get("max_count") and count > check["max_count"]:
                        issues.append(
                            {
                                "type": check["id"],
                                "severity": severity,
                                "description": f"{check['description']} ({count} found)",
                            }
                        )
                        score -= check["score_impact"]

                elif check_type == "image_alt_ratio":
                    all_images = soup.find_all("img")
                    if all_images:
                        without_alt = [img for img in all_images if not img.get("alt")]
                        if len(without_alt) > len(all_images) * check.get(
                            "threshold", 0.3
                        ):
                            issues.append(
                                {
                                    "type": check["id"],
                                    "severity": severity,
                                    "description": f"{len(without_alt)}/{len(all_images)} images missing alt text",
                                }
                            )
                            score -= check["score_impact"]

                elif check_type == "protocol_check":
                    if not url.startswith(check.get("protocol", "https://")):
                        issues.append(
                            {
                                "type": check["id"],
                                "severity": severity,
                                "description": check["description"],
                            }
                        )
                        score -= check["score_impact"]

                elif check_type == "load_time":
                    if response.elapsed.total_seconds() > check.get("threshold", 3.0):
                        issues.append(
                            {
                                "type": check["id"],
                                "severity": severity,
                                "description": f"{check['description']} ({response.elapsed.total_seconds():.2f}s)",
                            }
                        )
                        score -= check["score_impact"]

            tech_score = max(0, score)

            llm_config = self.audit_settings.get("llm_audit", {})
            qual_score = 100
            if self.ollama_enabled and llm_config.get("enabled"):
                if 0 <= tech_score <= 60:
                    text_content = self._strip_tags(html_content)[:2000]
                    llm_result = self._run_llm_audit(
                        business_name, text_content, llm_config
                    )
                    if llm_result:
                        qual_score = llm_result.get("qualitative_score", 100)
                        for obs in llm_result.get("observations", []):
                            issues.append(
                                {
                                    "type": f"llm_{obs.get('type', 'observation')}",
                                    "severity": self._normalize_severity(
                                        obs.get("severity", "info")
                                    ),
                                    "description": f"LLM: {obs.get('description')}",
                                }
                            )

            visual_config = self.audit_settings.get("visual_audit", {})
            vis_score = 100
            if self.ollama_enabled and visual_config.get("enabled"):
                base64_image = self._take_screenshot(url)
                if base64_image:
                    visual_result = self._run_visual_audit(
                        business_name, base64_image, visual_config
                    )
                    if visual_result:
                        vis_score = visual_result.get("visual_score", 100)
                        for obs in visual_result.get("observations", []):
                            issues.append(
                                {
                                    "type": f"visual_{obs.get('type', 'observation')}",
                                    "severity": self._normalize_severity(
                                        obs.get("severity", "info")
                                    ),
                                    "description": f"Visual: {obs.get('description')}",
                                }
                            )

            weights = self.audit_settings.get(
                "scoring_weights",
                {"technical_score": 0.35, "content_score": 0.35, "visual_score": 0.30},
            )

            final_score = (
                (tech_score * weights.get("technical_score", 0.35))
                + (qual_score * weights.get("content_score", 0.35))
                + (vis_score * weights.get("visual_score", 0.30))
            )
            score = final_score

        except requests.exceptions.Timeout:
            issues.append(
                {
                    "type": "timeout",
                    "severity": "critical",
                    "description": "Website timeout",
                }
            )
            score = 20
        except Exception as e:
            issues.append(
                {
                    "type": "error",
                    "severity": "critical",
                    "description": f"Audit error: {str(e)}",
                }
            )
            score = 30

        rules = self.audit_settings.get("qualification_rules", {})
        qualified = (
            score >= rules.get("target_score_min", 0)
            and score <= rules.get("target_score_max", 84)
            and len([i for i in issues if i["severity"] in ["warning", "critical"]])
            >= rules.get("min_issues_required", 2)
        )

        return {
            "url": url,
            "score": int(max(0, score)),
            "issues": issues,
            "qualified": 1 if qualified else 0,
            "discovered_info": discovered_info,
        }

    def _run_llm_audit(
        self, business_name: str, content: str, config: dict
    ) -> dict[str, Any] | None:
        """Run qualitative audit using Ollama."""
        prompt = config.get("prompt_template", "").format(
            business_name=business_name, content=content[:1500]
        )
        system_message = config.get(
            "system_message",
            "You are a professional website quality auditor. Output ONLY valid JSON.",
        )

        try:
            raw = llm.generate(
                model=config.get("model", "gemma:2b-instruct-q4_0"),
                prompt=prompt,
                system=system_message,
                format_json=True,
                timeout=30,
            )
            return json.loads(raw)
        except llm.OllamaError as e:
            self.log(f"LLM audit failed: {e}", "error")
            return None

    def refine_email_ollama(
        self, subject: str, body: str, instructions: str
    ) -> dict[str, str]:
        """Refine an existing email based on user instructions using Ollama."""
        if not self.ollama_enabled:
            return {"subject": subject, "body": body}

        prompt = f"""Refine this cold email based on instructions.

Instructions: {instructions}

Current Subject: {subject}
Current Body:
{body}

Return ONLY JSON: {{"subject": "refined subject line", "body": "refined email body"}}"""

        try:
            raw = llm.generate_with_retry(
                model=self._llm_settings["default_model"],
                prompt=prompt,
                system="You are a professional email editor. Output ONLY valid JSON.",
                format_json=True,
                max_retries=self._llm_settings["max_retries"],
                timeout=self._llm_settings["timeout_seconds"],
            )
            data = json.loads(raw)
            return {
                "subject": data.get("subject", subject),
                "body": data.get("body", body),
            }
        except llm.OllamaError as e:
            self.log(f"Email refinement failed: {e}", "error")
            return {"subject": subject, "body": body}

    def _parse_email_response(self, raw: str, business_name: str) -> dict[str, str]:
        """Parse email from LLM text response using delimiters."""
        text = raw.strip()

        filler_patterns = [
            r"^(Here is|Here's|This is|I have created|I've created|Below is|Please find)",
            r"^(Would you like|Do you want|Should I|Can I|Let me know if)",
            r"^(I hope this helps|I hope you find this useful|Feel free to)",
        ]

        for pattern in filler_patterns:
            text = re.sub(pattern, "", text, flags=re.IGNORECASE | re.MULTILINE)

        subject_match = re.search(
            r"(?:Subject:|SUBJECT:|\"subject\":)\s*[\"']?([^\"'\n]+)[\"']?", text
        )
        body_match = re.search(
            r"(?:Body:|BODY:|\"body\":)\s*[\"']?([^\"']+)[\"']?", text, re.DOTALL
        )

        subject = subject_match.group(1).strip() if subject_match else f"Quick question for {business_name}"
        body = body_match.group(1).strip() if body_match else text

        if "Best regards" not in body and "Sincerely" not in body:
            body += "\n\nBest regards,\n[Your Name]"

        return {"subject": subject, "body": body}

    @lru_cache(maxsize=128)
    def generate_email_ollama(
        self, business_name: str, issues_key: str, bucket: str
    ) -> dict:
        """Generate email using Ollama LLM with LRU caching."""
        return self._generate_email_uncached(business_name, issues_key, bucket)

    def _audit_single_lead(self, lead: dict) -> tuple:
        """Audit a single lead and discover contact info."""
        start_time = time.time()

        try:
            audit_result = self.audit_website(
                lead["website"],
                lead["business_name"],
                lead.get("bucket") or "default",
            )
            duration = time.time() - start_time

            if audit_result.get("discovered_info", {}).get("email"):
                self.log(
                    f"  ✓ Email found: {audit_result['discovered_info']['email']}",
                    "success",
                )

            return lead["id"], audit_result, duration
        except Exception as e:
            duration = time.time() - start_time
            error_result = {
                "url": lead.get("website", ""),
                "score": 0,
                "issues": [
                    {"type": "error", "severity": "critical", "description": str(e)}
                ],
                "qualified": 0,
                "discovered_info": {},
            }
            return lead["id"], error_result, duration

    def audit_leads(
        self,
        limit: int = 20,
        progress_callback: Callable[[int, int, str], None] | None = None,
    ) -> dict:
        """Audit pending leads - wrapped in managed_session for thread-safety."""
        with self.managed_session():
            self.log(f"\n{'=' * 60}")
            self.log("OUTREACH: Lead Auditing")
            self.log(f"{'=' * 60}")

            leads = get_pending_audits(limit)
            self.log(f"Auditing {len(leads)} leads...", "info")

            audited = 0
            qualified = 0
            skipped_no_email = 0
            audit_batch = []

            for i, lead in enumerate(leads, 1):
                lead_id, audit_result, duration = self._audit_single_lead(lead)

                if audit_result["score"] > 0:
                    audited += 1
                    audit_batch.append(
                        {
                            "lead_id": lead_id,
                            "score": audit_result["score"],
                            "issues_json": json.dumps(audit_result["issues"]),
                            "qualified": audit_result["qualified"],
                            "duration_seconds": duration,
                        }
                    )

                    if audit_result["qualified"]:
                        qualified += 1
                        contact_info = audit_result.get("discovered_info", {})
                        if contact_info.get("email"):
                            update_lead_contact_info(
                                lead_id,
                                {
                                    "email": contact_info["email"],
                                    "phone": contact_info.get("phone"),
                                },
                            )
                        else:
                            skipped_no_email += 1
                            self.log(
                                "  ⚠ Qualified but no email found",
                                "warning",
                            )

                if progress_callback:
                    progress_callback(i, len(leads), f"Auditing {lead['business_name']}")

            if audit_batch:
                save_audits_batch(audit_batch)

            self.log(f"\n{'=' * 60}")
            self.log(
                f"Auditing Complete: {audited} audited, {qualified} qualified, "
                f"{skipped_no_email} skipped (no contact)",
                "success",
            )
            self.log(f"{'=' * 60}\n")

            return {"audited": audited, "qualified": qualified}

    def _generate_single_email(self, lead: dict) -> dict | None:
        """Generate email for a single lead."""
        try:
            issues = json.loads(lead.get("issues_json", "[]"))

            start_time = time.time()
            email = self.generate_email_ollama(
                lead["business_name"],
                json.dumps(issues, sort_keys=True),
                lead.get("bucket") or "default",
            )
            duration = time.time() - start_time

            return {
                "lead_id": lead["id"],
                "subject": email["subject"],
                "body": email["body"],
                "status": "needs_review",
                "duration": duration,
            }
        except Exception as e:
            self.log(
                f"  Error generating email for {lead['business_name']}: {e}", "error"
            )
            return None

    def generate_emails(
        self,
        limit: int = 20,
        progress_callback: Callable[[int, int, str], None] | None = None,
    ) -> dict:
        """Generate emails for qualified leads - single-threaded with duration tracking."""
        self.log(f"\n{'=' * 60}")
        self.log("OUTREACH: Email Generation")
        self.log(f"{'=' * 60}")

        leads = get_qualified_leads(limit)
        self.log(f"Generating emails for {len(leads)} qualified leads...", "info")

        generated = 0
        email_batch = []

        for i, lead in enumerate(leads, 1):
            self.log(f"  [{i}/{len(leads)}] {lead['business_name']}", "info")

            email_data = self._generate_single_email(lead)
            if email_data:
                generated += 1
                email_batch.append(email_data)

            if progress_callback:
                progress_callback(i, len(leads), f"Generating for {lead['business_name']}")

        if email_batch:
            save_emails_batch(email_batch)

        self.log(f"\n{'=' * 60}")
        self.log(f"Email Generation Complete: {generated} emails generated", "success")
        self.log(f"{'=' * 60}\n")

        return {"generated": generated}
