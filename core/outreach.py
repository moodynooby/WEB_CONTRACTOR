"""Outreach Module: Lead Auditing + Email Generation (Stage B + Stage C)

Single-threaded design with efficient resource management:
- Browser context reused across audit operations
- LRU caching for email generation
- HTTP session reuse
- Proper Playwright lifecycle management
"""

import json
import time
from functools import lru_cache
from typing import Callable, Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, Page

from core import llm
from core.db_peewee import (
    update_lead_contact_info,
    get_pending_audits, save_audits_batch,
    get_qualified_leads, save_emails_batch,
)




class Outreach:
    """Consolidated Stage B (Auditing) + Stage C (Email Generation) - Single-threaded"""

    def __init__(
        self,
        logger: Optional[Callable] = None,
    ):
        self.logger = logger
        self.audit_settings = self._load_audit_settings()
        self.email_prompts = self._load_email_prompts()

        self._playwright = None

        self.ollama_enabled = llm.is_available()

    def _load_audit_settings(self) -> Dict:
        """Load audit settings from config file"""
        try:
            with open("config/audit_settings.json", "r") as f:
                return json.load(f)
        except Exception:
            return {
                "technical_checks": [],
                "llm_audit": {"enabled": False},
                "visual_audit": {"enabled": False},
            }

    def _load_email_prompts(self) -> Dict:
        """Load email prompts from config file"""
        try:
            with open("config/email_prompts.json", "r") as f:
                return json.load(f)
        except Exception:
            return {
                "cold_email": {"system_message": "", "prompt_template": ""},
                "email_signature": {},
            }

    def log(self, message: str, style: str = "") -> None:
        """Log message to provided logger or print"""
        if self.logger:
            self.logger(message, style)
        else:
            print(message)

    def _get_playwright_page(self) -> Optional[Page]:
        """Get or create Playwright page for visual audits (lazy init, reused)"""
        if self._playwright is None:
            try:
                self._playwright = sync_playwright().start().chromium.launch(headless=True)
            except Exception as e:
                self.log(
                    f"Failed to initialize Playwright for visual audit: {e}", "error"
                )
                return None
        return self._playwright.new_page()

    def _quit_playwright(self) -> None:
        """Properly shut down Playwright"""
        if self._playwright:
            try:
                self._playwright.close()
            except Exception as e:
                self.log(f"Unexpected error closing Playwright: {e}", "error")
            self._playwright = None

    def _take_screenshot(self, url: str) -> Optional[str]:
        """Capture website screenshot and return as base64 string"""
        page = self._get_playwright_page()
        if not page:
            return None

        try:
            page.goto(url, wait_until="networkidle")
            screenshot_bytes = page.screenshot(type="png")
            import base64

            return base64.b64encode(screenshot_bytes).decode("utf-8")
        except Exception as e:
            self.log(f"Failed to take screenshot: {e}", "error")
            return None

    def _run_visual_audit(
        self, business_name: str, base64_image: str, config: Dict
    ) -> Optional[Dict]:
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
        """Normalize severity to match DB constraints ('critical', 'warning', 'info')"""
        s = str(severity).lower().strip()
        if s in ["critical", "high", "error", "fatal"]:
            return "critical"
        if s in ["warning", "medium", "warn"]:
            return "warning"
        return "info"

    def deep_discovery(self, html_content: str, base_url: str) -> Dict:
        """Deep discovery of contact information from website HTML"""
        contact_info = {
            "email": None,
            "social_links": {},
            "contact_form_url": None,
            "phone": None,
        }

        soup = BeautifulSoup(html_content, "html.parser")

        for link in soup.find_all("a", href=True):
            href = link.get("href", "")

            if "@" in href and "mailto:" in href:
                contact_info["email"] = href.replace("mailto:", "").lower()
            elif not contact_info["email"]:
                text = link.get_text()
                if "@" in text and "." in text:
                    contact_info["email"] = text.lower()

            href_lower = href.lower()
            if "linkedin.com" in href_lower:
                contact_info["social_links"]["linkedin"] = href
            elif "facebook.com" in href_lower:
                contact_info["social_links"]["facebook"] = href
            elif "instagram.com" in href_lower:
                contact_info["social_links"]["instagram"] = href
            elif "twitter.com" in href_lower or "x.com" in href_lower:
                contact_info["social_links"]["twitter"] = href

            if any(k in href_lower for k in ["contact", "get-in-touch", "support"]):
                if not href.startswith("http"):
                    from urllib.parse import urljoin

                    contact_info["contact_form_url"] = urljoin(base_url, href)
                else:
                    contact_info["contact_form_url"] = href

        for link in soup.find_all("a", href=True):
            href = link.get("href", "")
            if href.startswith("tel:"):
                contact_info["phone"] = href.replace("tel:", "")

        return contact_info

    def _query_selector(self, html: str, selector: str) -> Optional[str]:
        """Query a single CSS selector from HTML content"""
        soup = BeautifulSoup(html, "html.parser")
        elem = soup.select_one(selector)
        return elem.get_text().strip() if elem else None

    def _query_selector_all(self, html: str, selector: str) -> List[str]:
        """Query all CSS selector matches from HTML content"""
        soup = BeautifulSoup(html, "html.parser")
        return [elem.get_text().strip() for elem in soup.select(selector)]

    def _find_all_tags(
        self,
        html: str,
        tag: str,
        attr: Optional[str] = None,
        attr_value: Optional[str] = None,
    ) -> List[Dict]:
        """Find all tags with optional attribute filter"""
        soup = BeautifulSoup(html, "html.parser")
        results = []

        for elem in soup.find_all(tag):
            if attr:
                value = elem.get(attr)
                if value:
                    results.append(
                        {"src": value} if tag in ["script", "img"] else {"href": value}
                    )
            else:
                text = elem.get_text(strip=True)
                if text:
                    results.append({"text": text})

        return results

    def _strip_tags(self, html: str) -> str:
        """Remove all script and style tags, then get text content"""
        soup = BeautifulSoup(html, "html.parser")

        for elem in soup(["script", "style"]):
            elem.decompose()

        return soup.get_text(separator=" ", strip=True)

    def audit_website(
        self,
        url: str,
        business_name: str = "this business",
        bucket_name: Optional[str] = None,
    ) -> Dict:
        """Audit website for technical and qualitative issues + Deep Discovery"""
        issues = []
        score = 100
        discovered_info = {
            "email": None,
            "social_links": {},
            "contact_form_url": None,
            "phone": None,
        }

        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            response = llm.get_session().get(url, headers=headers, timeout=10)
            html_content = response.text

            discovered_info = self.deep_discovery(html_content, url)

            if not discovered_info["email"] and discovered_info["contact_form_url"]:
                try:
                    c_resp = llm.get_session().get(
                        discovered_info["contact_form_url"], headers=headers, timeout=5
                    )
                    c_html = c_resp.text
                    c_info = self.deep_discovery(
                        c_html, discovered_info["contact_form_url"]
                    )
                    if c_info["email"]:
                        discovered_info["email"] = c_info["email"]
                    if c_info["phone"] and not discovered_info["phone"]:
                        discovered_info["phone"] = c_info["phone"]
                except requests.RequestException as e:
                    self.log(
                        f"Error fetching contact page {discovered_info['contact_form_url']}: {e}",
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
                    elem = self._query_selector(html_content, selector)
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
                    count = len(self._query_selector_all(html_content, selector))
                    if (
                        check.get("max_count") is not None
                        and count > check["max_count"]
                    ):
                        issues.append(
                            {
                                "type": check["id"],
                                "severity": severity,
                                "description": f"{check['description']} ({count} found)",
                            }
                        )
                        score -= check["score_impact"]

                elif check_type == "image_alt_ratio":
                    soup = BeautifulSoup(html_content, "html.parser")
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

                elif check_type == "script_match":
                    patterns = check.get("patterns", [])
                    found = False
                    scripts = self._find_all_tags(html_content, "script", "src")
                    for script in scripts:
                        src = script.get("src", "")
                        if any(p in src for p in patterns):
                            found = True
                            break
                    if not found:
                        issues.append(
                            {
                                "type": check["id"],
                                "severity": severity,
                                "description": check["description"],
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

                elif check_type == "link_match":
                    patterns = check.get("patterns", [])
                    found = False
                    links = self._find_all_tags(html_content, "a", "href")
                    for link in links:
                        href = link.get("href", "").lower()
                        if any(p.lower() in href for p in patterns):
                            found = True
                            break
                    if not found:
                        issues.append(
                            {
                                "type": check["id"],
                                "severity": severity,
                                "description": check["description"],
                            }
                        )
                        score -= check["score_impact"]

                elif check_type == "text_match":
                    patterns = check.get("patterns", [])
                    text = self._strip_tags(html_content).lower()
                    found = any(p.lower() in text for p in patterns)
                    if not found:
                        issues.append(
                            {
                                "type": check["id"],
                                "severity": severity,
                                "description": check["description"],
                            }
                        )
                        score -= check["score_impact"]

            llm_config = self.audit_settings.get("llm_audit", {})
            qual_score = 100
            if self.ollama_enabled and llm_config.get("enabled"):
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
                self.log("  Capturing screenshot for visual audit...", "info")
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
                        self.log(
                            f"  Visual audit complete (Score: {vis_score})", "success"
                        )

            weights = self.audit_settings.get(
                "scoring_weights",
                {"technical_score": 0.35, "content_score": 0.35, "visual_score": 0.30},
            )

            tech_score = max(0, score)

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
        target_min = rules.get("target_score_min", 40)
        target_max = rules.get("target_score_max", 84)
        min_issues = rules.get("min_issues_required", 2)

        qualified = (
            score >= target_min
            and score <= target_max
            and len([i for i in issues if i["severity"] in ["warning", "critical"]])
            >= min_issues
        )

        return {
            "url": url,
            "score": int(max(0, score)),
            "issues": issues,
            "qualified": 1 if qualified else 0,
            "discovered_info": discovered_info,
        }

    def _run_llm_audit(
        self, business_name: str, content: str, config: Dict
    ) -> Optional[Dict]:
        """Run qualitative audit using Ollama."""
        prompt_template = config.get("prompt_template", "")
        system_message = config.get(
            "system_message",
            "You are a professional website quality auditor. Output ONLY valid JSON.",
        )
        prompt = prompt_template.format(
            business_name=business_name, content=content[:1500]
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

    def refine_email_ollama(self, subject: str, body: str, instructions: str) -> Dict:
        """Refine an existing email based on user instructions using Ollama ."""
        if not self.ollama_enabled:
            return {"subject": subject, "body": body}

        prompt = f"""Refine this cold email based on instructions.

Instructions: {instructions}

Current Subject: {subject}
Current Body:
{body}

Return ONLY JSON:
{{"subject": "refined subject line", "body": "refined email body"}}"""

        try:
            raw = llm.generate_with_retry(
                model="gemma:2b-instruct-q4_0",
                prompt=prompt,
                system="You are a professional email editor. Output ONLY valid JSON. Preserve the signature if present, or add one if missing.",
                format_json=True,
                max_retries=3,
                timeout=60,
            )
            data = json.loads(raw)
            return {
                "subject": data.get("subject", subject),
                "body": data.get("body", body),
            }
        except llm.OllamaError as e:
            self.log(f"Email refinement failed: {e}", "error")
            return {"subject": subject, "body": body}

    def _generate_email_uncached(
        self, business_name: str, issues_key: str, bucket: str
    ) -> Dict:
        """Uncached email generation without retry logic."""
        if not self.ollama_enabled:
            raise Exception("Ollama is not enabled. Cannot generate email.")

        issues = json.loads(issues_key)

        sorted_issues = sorted(
            issues,
            key=lambda x: (
                0 if x.get("type", "").startswith("llm_") else 1,
                0
                if x.get("severity") == "critical"
                else 1
                if x.get("severity") == "warning"
                else 2,
            ),
        )

        issue_summary = "\n".join([f"- {i['description']}" for i in sorted_issues[:6]])

        prompt_template = self.email_prompts.get("cold_email", {}).get(
            "prompt_template", ""
        )
        system_message = self.email_prompts.get("cold_email", {}).get(
            "system_message",
            "You are a professional email writer. Output ONLY valid JSON.",
        )
        prompt = prompt_template.format(
            business_name=business_name, issue_summary=issue_summary
        )

        try:
            raw = llm.generate(
                model="gemma:2b-instruct-q4_0",
                prompt=prompt,
                system=system_message,
                format_json=True,
                timeout=60,
            )
        except llm.OllamaError as e:
            self.log(f"Error generating email: {e}", "error")
            raise

        try:
            data = json.loads(raw)
            body = data.get("body", "")
            if not body:
                raise Exception("Missing body in LLM response")

            if "Best regards" in body or "Manas Doshi" in body:
                body = body.split("Best regards")[0].split("Sincerely")[0].strip()

            signature = self.email_prompts.get("email_signature", {}).get(
                "template",
                "\n\nBest regards,\nManas Doshi,\nFuture Forwards - https://man27.netlify.app/services",
            )
            if "{name}" in signature or "{company}" in signature:
                signature = signature.format(
                    name=self.email_prompts.get("email_signature", {}).get(
                        "name", "Manas Doshi"
                    ),
                    company=self.email_prompts.get("email_signature", {}).get(
                        "company", "Future Forwards"
                    ),
                    website=self.email_prompts.get("email_signature", {}).get(
                        "website", "https://man27.netlify.app/services"
                    ),
                )
            final_body = body.strip() + signature

            return {
                "subject": data.get("subject", f"Quick note about {business_name}"),
                "body": final_body,
            }
        except json.JSONDecodeError as e:
            self.log(f"Failed to parse email JSON: {e}\nRaw: {raw}", "error")
            raise

    @lru_cache(maxsize=128)
    def generate_email_ollama(
        self, business_name: str, issues_key: str, bucket: str
    ) -> Dict:
        """Generate email using Ollama LLM with LRU caching.

        Rate limiting is handled by the Ollama client (Semaphore).
        """
        return self._generate_email_uncached(business_name, issues_key, bucket)

    def _audit_single_lead(self, lead: Dict) -> Tuple[int, Dict, float]:
        """Audit a single lead"""
        start_time = time.time()

        try:
            audit_result = self.audit_website(
                lead["website"],
                lead["business_name"],
                lead.get("bucket") or "default",
            )
            duration = time.time() - start_time

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
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> Dict:
        """Audit pending leads - single-threaded with duration tracking"""
        self.log(f"\n{'=' * 60}")
        self.log("OUTREACH: Lead Auditing")
        self.log(f"{'=' * 60}")

        leads = get_pending_audits(limit)
        self.log(f"Auditing {len(leads)} leads...", "info")

        audited = 0
        qualified = 0
        audit_batch = []

        try:
            for i, lead in enumerate(leads, 1):
                self.log(f"\n[{i}/{len(leads)}] {lead['business_name']}", "info")

                lead_id, audit_result, duration = self._audit_single_lead(lead)

                if "discovered_info" in audit_result:
                    info = audit_result["discovered_info"]
                    update_lead_contact_info(lead_id, info)
                    if info.get("email"):
                        self.log(f"  Found email: {info['email']}", "success")
                    if info.get("social_links"):
                        self.log(
                            f"  Found {len(info['social_links'])} social links",
                            "success",
                        )

                audit_batch.append(
                    {
                        "lead_id": lead_id,
                        "data": audit_result,
                        "duration": duration,
                    }
                )

                audited += 1
                if audit_result["qualified"]:
                    qualified += 1
                    self.log(
                        f"  Qualified (Score: {audit_result['score']}, Issues: {len(audit_result['issues'])}, Time: {duration:.1f}s)",
                        "success",
                    )
                else:
                    self.log(
                        f"  Not qualified (Score: {audit_result['score']}, Time: {duration:.1f}s)",
                        "error",
                    )

                if progress_callback:
                    progress_callback(i, len(leads), lead["business_name"])

                self.log(
                    f"  Score: {audit_result['score']}, Qualified: {bool(audit_result['qualified'])}",
                    "success" if audit_result["qualified"] else "info",
                )

            if audit_batch:
                save_audits_batch(audit_batch)

        finally:
            self._quit_playwright()

        self.log(f"\n{'=' * 60}")
        self.log(
            f"Auditing Complete: {audited} audited, {qualified} qualified", "success"
        )
        self.log(f"{'=' * 60}\n")

        return {"audited": audited, "qualified": qualified}

    def _generate_single_email(self, lead: Dict) -> Optional[Dict]:
        """Generate email for a single lead"""
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
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> Dict:
        """Generate emails for qualified leads - single-threaded with duration tracking"""
        self.log(f"\n{'=' * 60}")
        self.log("OUTREACH: Email Generation")
        self.log(f"{'=' * 60}")

        leads = get_qualified_leads(limit)
        self.log(f"Generating emails for {len(leads)} qualified leads...", "info")

        generated = 0
        email_batch = []

        for i, lead in enumerate(leads, 1):
            self.log(f"\n[{i}/{len(leads)}] {lead['business_name']}", "info")

            result = self._generate_single_email(lead)
            if result:
                email_batch.append(result)
                generated += 1
                self.log(
                    f"  Email generated (Time: {result['duration']:.1f}s)",
                    "success",
                )

            if progress_callback:
                progress_callback(i, len(leads), lead["business_name"])

            self.log(
                f"  {'Generated' if result else 'Failed'}",
                "success" if result else "error",
            )

        if email_batch:
            save_emails_batch(email_batch)

        self.log(f"\n{'=' * 60}")
        self.log(f"Email Generation Complete: {generated} emails created", "success")
        self.log(f"{'=' * 60}\n")

        return {"generated": generated}
