"""Outreach Module: Lead Auditing + Email Generation (Stage B + Stage C)

Efficient resource management with per-operation browser contexts:
- Fresh browser context created for each audit operation
- LRU caching for email generation
- HTTP session reuse
- Proper Playwright lifecycle management
"""

import json
import time
from functools import lru_cache
from typing import Any, Callable, Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from contextlib import contextmanager

from core import llm
from core.db_repository import (
    update_lead_contact_info,
    get_pending_audits, save_audits_batch,
    get_qualified_leads, save_emails_batch,
)


def _load_json_config(filename: str) -> dict:
    """Load JSON config file (shared helper)."""
    from pathlib import Path
    settings_path = Path(__file__).parent.parent / "config" / filename
    try:
        with open(settings_path, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


class Outreach:
    """Consolidated Stage B (Auditing) + Stage C (Email Generation) - Single-threaded"""

    def __init__(
        self,
        logger: Callable | None = None,
    ):
        self.logger = logger
        self.audit_settings = _load_json_config("audit_settings.json")
        self.email_prompts = _load_json_config("email_prompts.json")
        self.ollama_enabled = llm.is_available()
        self._llm_settings = _load_json_config("app_settings.json").get("llm_settings", {})

    def log(self, message: str, style: str = "") -> None:
        """Log message to provided logger or print"""
        if self.logger:
            self.logger(message, style)
        else:
            print(message)

    @contextmanager
    def managed_session(self):
        """Context manager for audit session - creates fresh browser context per operation

        Always creates a new browser context for reliability and proper cleanup.
        """
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
        """Get new Playwright page from current context"""
        if not hasattr(self, '_context') or self._context is None:
            raise RuntimeError("Outreach must be used within managed_session() for browser tasks")
        return self._context.new_page()  # type: ignore[no-any-return]

    def _take_screenshot(self, url: str) -> str | None:
        """Capture website screenshot and return as base64 string"""
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
    ) -> Optional[Dict[str, Any]]:
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
            return json.loads(raw)  # type: ignore[no-any-return]
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

    def deep_discovery(self, html_content: str, base_url: str) -> dict:
        """Deep discovery of contact information from website HTML

        Returns early if email is found to optimize performance.
        """
        contact_info: dict = {
            "email": None,
            "social_links": {},
            "contact_form_url": None,
            "phone": None,
        }

        soup = BeautifulSoup(html_content, "html.parser")
        email_found = False

        for link in soup.find_all("a", href=True):
            href = str(link.get("href", "") or "")
            href_lower = href.lower()

            if not email_found:
                if "@" in href and "mailto:" in href:
                    contact_info["email"] = href.replace("mailto:", "").lower()
                    email_found = True
                elif "@" in href and "." in href and len(href) < 100:
                    contact_info["email"] = href.lower()
                    email_found = True

            if not email_found:
                text = str(link.get_text() or "")
                if "@" in text and "." in text and len(text) < 100:
                    contact_info["email"] = text.lower()
                    email_found = True

            if "linkedin.com" in href_lower:
                contact_info["social_links"]["linkedin"] = href
            elif "facebook.com" in href_lower:
                contact_info["social_links"]["facebook"] = href
            elif "instagram.com" in href_lower:
                contact_info["social_links"]["instagram"] = href
            elif "twitter.com" in href_lower or "x.com" in href_lower:
                contact_info["social_links"]["twitter"] = href

            if not contact_info["contact_form_url"]:
                if any(k in href_lower for k in ["contact", "get-in-touch", "support"]):
                    if not href.startswith("http"):
                        from urllib.parse import urljoin
                        contact_info["contact_form_url"] = urljoin(base_url, href)
                    else:
                        contact_info["contact_form_url"] = href

        if not email_found:
            import re
            email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
            text_content = soup.get_text()
            emails = re.findall(email_pattern, text_content)
            if emails:
                for email in emails:
                    if not any(x in email.lower() for x in ['example', 'domain', 'placeholder']):
                        contact_info["email"] = email.lower()
                        break

        for link in soup.find_all("a", href=True):
            href = str(link.get("href", "") or "")
            if href.startswith("tel:"):
                contact_info["phone"] = href.replace("tel:", "")
                break

        return contact_info

    def _query_selector(self, html: str, selector: str) -> str | None:
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
    ) -> list:
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
    ) -> dict:
        """Audit website for technical and qualitative issues + Deep Discovery

        Optimizations:
        - Returns contact info immediately if email is found
        - Skips expensive LLM/visual audits if email already discovered
        """
        issues: List[Dict[str, Any]] = []
        score = 100
        discovered_info: dict = {
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

            tech_score = max(0, score)

            llm_config = self.audit_settings.get("llm_audit", {})
            qual_score = 100
            if self.ollama_enabled and llm_config.get("enabled"):
                if 0 <= tech_score <= 60:
                    self.log(f"  Technical score {tech_score} in range, running LLM audit...", "info")
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
                else:
                    self.log(f"  Technical score {tech_score} out of range, skipping LLM audit.", "info")

            visual_config = self.audit_settings.get("visual_audit", {})
            vis_score = 100
            if self.ollama_enabled and visual_config.get("enabled"):
                if 0 <= tech_score <= 65:
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
        target_min = rules.get("target_score_min", 0)
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
        self, business_name: str, content: str, config: dict
    ) -> Optional[Dict[str, Any]]:
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
            return json.loads(raw)  # type: ignore[no-any-return]
        except llm.OllamaError as e:
            self.log(f"LLM audit failed: {e}", "error")
            return None

    def refine_email_ollama(self, subject: str, body: str, instructions: str) -> Dict[str, str]:
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
                model=self._llm_settings["default_model"],
                prompt=prompt,
                system="You are a professional email editor. Output ONLY valid JSON. Preserve the signature if present, or add one if missing.",
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

    def _parse_email_response(self, raw: str, business_name: str) -> Dict[str, str]:
        """Parse email from LLM text response using delimiters"""
        import re
        
        text = raw.strip()
        
        filler_patterns = [
            r'^(Here is|Here\'s|This is|I have created|I\'ve created|Below is|Please find)',
            r'^(Would you like|Do you want|Should I|Can I|Let me know if)',
            r'^(I hope this helps|I hope you find this useful|Feel free to)',
            r'^(Note:|Important:|Remember:|Please note)',
            r'^(I\'ve written|I have written|I wrote|I created)',
            r'^(Your email is ready|Here you go|Here it is)',
            r'^(As requested|As you asked|Per your request)',
            r'(Would you like me to|Do you want me to|Should I also|Can I also)',
            r'(Let me know if you need|Feel free to ask|Happy to revise)',
            r'(I can adjust|I can modify|I can change|Let me know if)',
            r'(This is a draft|This draft|The above email)',
        ]
        
        for pattern in filler_patterns:
            text = re.sub(pattern, '', text, flags=re.IGNORECASE | re.MULTILINE)
        
        lines = text.split('\n')
        cleaned_lines = []
        for line in lines:
            line_stripped = line.strip()
            if re.match(r'^(Here|Would|Do|Should|Can|Let|I hope|Feel|Note|Important|Please find|As requested)', line_stripped, re.IGNORECASE):
                continue
            if re.match(r'^[-*]\s*(Here|Would|Do|Should|Can|Let|I hope|Feel|Note)', line_stripped, re.IGNORECASE):
                continue
            cleaned_lines.append(line)
        text = '\n'.join(cleaned_lines)
        
        subject_patterns = [
            (r'\[SUBJECT\]\s*(.+?)\s*\[/SUBJECT\]', re.IGNORECASE | re.DOTALL),
            (r'(?:SUBJECT|Subject)[:\s]+(.+?)(?:\n|$)', re.IGNORECASE | re.MULTILINE),
            (r'\*\*Subject:\*\*\s*(.+?)(?:\n|$)', re.IGNORECASE | re.MULTILINE),
        ]
        
        subject = None
        for pattern, flags in subject_patterns:
            match = re.search(pattern, text, flags)
            if match:
                subject = match.group(1).strip()
                subject = re.sub(r'\[/?SUBJECT\]', '', subject, flags=re.IGNORECASE).strip()
                break
        
        if not subject:
            lines = text.split('\n')
            for line in lines:
                line = line.strip()
                skip_patterns = [
                    r'^\[',  
                    r'^(Dear|Hello|Hi|Good morning|Good afternoon)',  
                    r'^(Here is|Here\'s|This is|I have|I\'m writing|I am writing)',  
                    r'^(Would|Do|Should|Can|Let me|I hope|Feel free)',  
                    r'^[-*•]',  
                    r'^\d+\.',  
                ]
                should_skip = False
                for skip_pattern in skip_patterns:
                    if re.match(skip_pattern, line, re.IGNORECASE):
                        should_skip = True
                        break
                if not should_skip and line and len(line) < 100:
                    subject = line
                    break

        if not subject:
            subject = f"Quick note about {business_name}"

        subject = re.sub(r'\[/?\w+\]', '', subject)  
        subject = re.sub(r'\*+', '', subject)  
        subject = subject.strip(' #:\"\'')  
        subject = re.sub(r'\s+', ' ', subject)  
        
        body_patterns = [
            (r'\[BODY\]\s*(.+?)\s*\[/BODY\]', re.IGNORECASE | re.DOTALL),
            (r'(?:BODY|Body)[:\s]+(.+?)(?:\n\s*\n|\[END\]|$)', re.IGNORECASE | re.DOTALL),
            (r'\*\*Body:\*\*\s*(.+?)(?:\n\s*\n|$)', re.IGNORECASE | re.DOTALL),
        ]
        
        body = None
        for pattern, flags in body_patterns:
            match = re.search(pattern, text, flags)
            if match:
                body = match.group(1).strip()
                break
        
        if not body:
            body = re.sub(r'\[SUBJECT\].*?\[/SUBJECT\]', '', text, flags=re.IGNORECASE | re.DOTALL)
            body = re.sub(r'(?:SUBJECT|Subject)[:\s]+.+?(?:\n|$)', '', body, flags=re.IGNORECASE)
            body = re.sub(r'\[/?BODY\]', '', body, flags=re.IGNORECASE)
            body = body.strip()
        
        if "Best regards" in body or "Manas Doshi" in body or "Sincerely" in body or "Regards" in body:
            body = re.split(r'(?:Best regards|Sincerely|Regards|Kind regards|Warm regards)', body, flags=re.IGNORECASE)[0].strip()
        
        body = re.sub(r'\[/?\w+\]', '', body)
        body = re.sub(r'\*+', '', body)  
        body = re.sub(r'#{2,}', '', body)  
        body = re.sub(r'\[website[^\]]*\]', 'your website', body, flags=re.IGNORECASE)
        body = re.sub(r'\[company[^\]]*\]', business_name, body, flags=re.IGNORECASE)
        body = re.sub(r'\[business[^\]]*\]', business_name, body, flags=re.IGNORECASE)
        body = re.sub(r' +', ' ', body)
        body = re.sub(r'\n\s*\n', '\n\n', body)
        body = '\n'.join(line.strip() for line in body.split('\n') if line.strip())
        
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
        
        return {"subject": subject, "body": final_body}

    def _generate_email_uncached(
        self, business_name: str, issues_key: str, bucket: str
    ) -> dict:
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
            "You are a professional email writer. Use [SUBJECT] and [BODY] tags.",
        )
        prompt = prompt_template.format(
            business_name=business_name, issue_summary=issue_summary
        )

        try:
            raw = llm.generate(
                model=self._llm_settings["default_model"],
                prompt=prompt,
                system=system_message,
                format_json=False,
                timeout=self._llm_settings["timeout_seconds"],
            )
        except llm.OllamaError as e:
            self.log(f"Error generating email: {e}", "error")
            raise

        return self._parse_email_response(raw, business_name)

    @lru_cache(maxsize=128)
    def generate_email_ollama(
        self, business_name: str, issues_key: str, bucket: str
    ) -> Dict:
        """Generate email using Ollama LLM with LRU caching.

        Rate limiting is handled by the Ollama client (Semaphore).
        """
        return self._generate_email_uncached(business_name, issues_key, bucket)

    def _audit_single_lead(self, lead: Dict) -> Tuple[int, Dict, float]:
        """Audit a single lead and discover contact info.
        
        Returns early if email is found during discovery to optimize performance.
        """
        start_time = time.time()

        try:
            audit_result = self.audit_website(
                lead["website"],
                lead["business_name"],
                lead.get("bucket") or "default",
            )
            duration = time.time() - start_time

            if audit_result.get("discovered_info", {}).get("email"):
                self.log(f"  ✓ Email found: {audit_result['discovered_info']['email']}", "success")

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
        """Audit pending leads - wrapped in managed_session for thread-safety
        
        Optimizations:
        - Skips leads that already have email addresses
        - Stops processing a lead once email is found
        """
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
                self.log(f"\n[{i}/{len(leads)}] {lead['business_name']}", "info")

                lead_id, audit_result, duration = self._audit_single_lead(lead)
                discovered_info = audit_result.get("discovered_info", {})

                has_email = bool(discovered_info.get("email"))
                has_contact_form = bool(discovered_info.get("contact_form_url"))
                
                if not has_email and not has_contact_form:
                    skipped_no_email += 1
                    self.log("  ✗ No contact info found - skipping lead", "error")
                    continue

                if discovered_info:
                    update_lead_contact_info(lead_id, discovered_info)
                    if has_email:
                        self.log(f"  ✓ Email: {discovered_info['email']}", "success")
                    if has_contact_form:
                        self.log(f"  ✓ Contact form: {discovered_info['contact_form_url']}", "success")
                    if discovered_info.get("social_links"):
                        self.log(
                            f"  ✓ Found {len(discovered_info['social_links'])} social links",
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
                        f"  ✓ Qualified (Score: {audit_result['score']}, Issues: {len(audit_result['issues'])}, Time: {duration:.1f}s)",
                        "success",
                    )
                else:
                    self.log(
                        f"  ✗ Not qualified (Score: {audit_result['score']}, Time: {duration:.1f}s)",
                        "error",
                    )

                if progress_callback:
                    progress_callback(i, len(leads), lead["business_name"])

            if audit_batch:
                save_audits_batch(audit_batch)

            self.log(f"\n{'=' * 60}")
            self.log(
                f"Auditing Complete: {audited} audited, {qualified} qualified, {skipped_no_email} skipped (no contact)", "success"
            )
            self.log(f"{'=' * 60}\n")

            return {"audited": audited, "qualified": qualified}

    def _generate_single_email(self, lead: dict) -> Optional[Dict[str, Any]]:
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
            }  # type: ignore[no-any-return]
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
