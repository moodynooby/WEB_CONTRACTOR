"""Multi-Agent Audit System

Specialized agents for different audit aspects, configured via audit_settings.json
and executed sequentially with early exit.

Agents:
- TechnicalAgent: SEO, performance, security (HTTP-only, 2-3s)
- ContactAgent: Email/phone discovery (HTTP-only, 2-3s)
- ContentAgent: Copy quality, CTAs (LLM-based, 3-5s)
- BusinessAgent: Industry-specific checks (LLM-based, 3-5s)
- VisualAgent: Design, UX analysis (VLM + screenshot, 5-8s, optional)
"""

import json
import re
import time
from abc import ABC, abstractmethod
from typing import Any, Callable, TypedDict
from urllib.parse import parse_qs, urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from email_validator import EmailNotValidError, validate_email

from core import llm


class AgentResult(TypedDict, total=False):
    """Standardized result from any audit agent."""
    score: int
    issues: list[dict[str, Any]]
    duration: float
    agent_name: str
    metadata: dict[str, Any]


class BaseAgent(ABC):
    """Base class for all audit agents."""

    def __init__(
        self,
        config: dict,
        logger: Callable[[str, str], None] | None = None,
    ) -> None:
        self.config = config
        self.logger = logger or (lambda msg, style: print(f"[{style}] {msg}"))
        self.enabled = config.get("enabled", True)
        self.weight = config.get("weight", 1.0)
        self.timeout = config.get("timeout", 30)

    @abstractmethod
    def execute(
        self,
        url: str,
        business_name: str,
        bucket: str,
        html_content: str | None = None,
        soup: BeautifulSoup | None = None,
        response: requests.Response | None = None,
        screenshot_base64: str | None = None,
        previous_results: dict[str, AgentResult] | None = None,
    ) -> AgentResult:
        """Execute the agent's audit logic.

        Args:
            url: Website URL
            business_name: Business name
            bucket: Bucket/category name
            html_content: Raw HTML (optional, may be provided by orchestrator)
            soup: Parsed BeautifulSoup object (optional)
            response: HTTP response object (optional)
            screenshot_base64: Base64 screenshot (optional, for visual agents)
            previous_results: Results from previously executed agents (optional)

        Returns:
            AgentResult with score, issues, duration, and metadata
        """
        pass

    def log(self, message: str, style: str = "") -> None:
        """Log message with agent prefix."""
        agent_name = self.__class__.__name__.replace("Agent", "")
        self.logger(f"[{agent_name}] {message}", style)

    def _fetch_url(
        self, url: str
    ) -> tuple[str, BeautifulSoup, requests.Response] | None:
        """Fetch URL and return html, soup, response. Returns None on error."""
        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            resp = requests.get(url, headers=headers, timeout=10)
            return resp.text, BeautifulSoup(resp.text, "html.parser"), resp
        except Exception as e:
            self.log(f"Fetch failed: {e}", "error")
            return None

    def _normalize_severity(self, severity: str) -> str:
        """Normalize severity to match DB constraints (critical/warning/info)."""
        mapping = {
            "critical": ["critical", "high", "error", "fatal"],
            "warning": ["warning", "medium", "warn"],
        }
        s = str(severity).lower().strip()
        for normalized, values in mapping.items():
            if s in values:
                return normalized
        return "info"

    def _call_llm_with_retry(
        self,
        model: str,
        prompt: str,
        system: str,
        format_json: bool = True,
        image_base64: str | None = None,
        max_retries: int = 2,
    ) -> tuple[dict, dict]:
        """Call LLM with retry logic for timeouts/invalid JSON.

        Returns:
            Tuple of (result_dict, error_dict). If successful, error_dict is empty.
        """
        timeouts = [self.timeout, 15, 10]

        for attempt in range(max_retries + 1):
            try:
                current_timeout = timeouts[min(attempt, len(timeouts) - 1)]
                if attempt > 0:
                    self.log(f"  Retry {attempt}/{max_retries} with {current_timeout}s timeout", "warning")

                raw = llm.generate(
                    model=model,
                    prompt=prompt,
                    system=system,
                    format_json=format_json,
                    timeout=current_timeout,
                )
                try:
                    return json.loads(raw), {}
                except json.JSONDecodeError as e:
                    self.log(f"LLM returned invalid JSON: {e}", "warning")
                    if attempt < max_retries:
                        continue
                    return {}, {"error": "invalid_json", "raw": raw[:200]}

            except llm.OllamaError as e:
                self.log(f"LLM attempt {attempt + 1} failed: {e}", "warning")
                if attempt >= max_retries:
                    return {}, {"error": "ollama_error", "message": str(e)}
            except Exception as e:
                self.log(f"LLM unexpected error: {e}", "error")
                if attempt >= max_retries:
                    return {}, {"error": "unexpected", "message": str(e)}

        return {}, {"error": "max_retries_exceeded"}


class TechnicalAgent(BaseAgent):
    """Technical audit agent: SEO, performance, security checks.

    Fast HTTP-only checks that don't require browser or LLM.
    """

    def __init__(
        self,
        config: dict,
        logger: Callable[[str, str], None] | None = None,
    ) -> None:
        super().__init__(config, logger)
        self.checks = config.get("technical_checks", [])

    def execute(
        self,
        url: str,
        business_name: str,
        bucket: str,
        html_content: str | None = None,
        soup: BeautifulSoup | None = None,
        response: requests.Response | None = None,
        screenshot_base64: str | None = None,
        previous_results: dict[str, AgentResult] | None = None,
    ) -> AgentResult:
        start_time = time.time()
        issues: list[dict[str, Any]] = []
        score = 100

        if not html_content or not soup or not response:
            fetched = self._fetch_url(url)
            if fetched is None:
                return AgentResult(
                    score=0,
                    issues=[{"type": "error", "severity": "critical", "description": "Fetch failed"}],
                    duration=time.time() - start_time,
                    agent_name="Technical",
                    metadata={"error": "fetch_failed"},
                )
            html_content, soup, response = fetched

        for check in self.checks:
            check_type = check.get("type")
            selector = check.get("selector")
            severity = self._normalize_severity(check.get("severity", "info"))

            if check_type == "html_exists":
                elem = soup.select_one(selector)
                if not elem or (
                    check.get("min_length") and len(elem.get_text().strip()) < check["min_length"]
                ):
                    issues.append({
                        "type": check["id"],
                        "severity": severity,
                        "description": check["description"],
                        "remediation": check.get("remediation"),
                    })
                    score -= check["score_impact"]

            elif check_type == "html_count":
                count = len(soup.select(selector))
                if check.get("max_count") and count > check["max_count"]:
                    issues.append({
                        "type": check["id"],
                        "severity": severity,
                        "description": f"{check['description']} ({count} found)",
                        "remediation": check.get("remediation"),
                    })
                    score -= check["score_impact"]

            elif check_type == "image_alt_ratio":
                all_images = soup.find_all("img")
                if all_images:
                    without_alt = [img for img in all_images if not img.get("alt")]
                    if len(without_alt) > len(all_images) * check.get("threshold", 0.3):
                        issues.append({
                            "type": check["id"],
                            "severity": severity,
                            "description": f"{len(without_alt)}/{len(all_images)} images missing alt text",
                            "remediation": check.get("remediation"),
                        })
                        score -= check["score_impact"]

            elif check_type == "protocol_check":
                if not url.startswith(check.get("protocol", "https://")):
                    issues.append({
                        "type": check["id"],
                        "severity": severity,
                        "description": check["description"],
                        "remediation": check.get("remediation"),
                    })
                    score -= check["score_impact"]

            elif check_type == "load_time":
                load_time = response.elapsed.total_seconds()
                if load_time > check.get("threshold", 3.0):
                    issues.append({
                        "type": check["id"],
                        "severity": severity,
                        "description": f"{check['description']} ({load_time:.2f}s)",
                        "remediation": check.get("remediation"),
                    })
                    score -= check["score_impact"]

        return AgentResult(
            score=max(0, score),
            issues=issues,
            duration=time.time() - start_time,
            agent_name="Technical",
            metadata={
                "checks_run": len(self.checks),
                "load_time": response.elapsed.total_seconds(),
            },
        )


class ContentAgent(BaseAgent):
    """Content audit agent: Copy quality, CTAs, value proposition.

    Uses LLM to analyze text content for messaging effectiveness.
    """

    def __init__(
        self,
        config: dict,
        logger: Callable[[str, str], None] | None = None,
    ) -> None:
        super().__init__(config, logger)
        self.llm_config = config
        self.ollama_enabled = llm.is_available()

    def execute(
        self,
        url: str,
        business_name: str,
        bucket: str,
        html_content: str | None = None,
        soup: BeautifulSoup | None = None,
        response: requests.Response | None = None,
        screenshot_base64: str | None = None,
        previous_results: dict[str, AgentResult] | None = None,
    ) -> AgentResult:
        start_time = time.time()
        issues: list[dict[str, Any]] = []
        score = 100

        if not self.ollama_enabled or not self.enabled:
            return AgentResult(
                score=score,
                issues=issues,
                duration=time.time() - start_time,
                agent_name="Content",
                metadata={"skipped": "LLM disabled or agent disabled"},
            )

        if not html_content:
            fetched = self._fetch_url(url)
            if fetched is None:
                return AgentResult(
                    score=0,
                    issues=[{"type": "error", "severity": "critical", "description": "Fetch failed"}],
                    duration=time.time() - start_time,
                    agent_name="Content",
                    metadata={"error": "fetch_failed"},
                )
            html_content, soup, _ = fetched

        soup_obj = BeautifulSoup(html_content, "html.parser")
        for elem in soup_obj(["script", "style", "meta", "link"]):
            elem.decompose()
        text_content = soup_obj.get_text(separator=" ", strip=True)[:2000]

        system_message = self.llm_config.get(
            "system_message",
            "You are a professional content auditor. Output ONLY valid JSON.",
        )

        max_retries = 2
        content_lengths = [1000, 500, 200]

        for attempt in range(max_retries + 1):
            current_content_len = content_lengths[min(attempt, len(content_lengths) - 1)]

            prompt_retry = self.llm_config.get("prompt_template", "").format(
                business_name=business_name,
                bucket=bucket,
                content=text_content[:current_content_len],
            )

            if attempt > 0:
                self.log(f"  Content audit retry {attempt}/{max_retries} with {current_content_len} chars", "warning")

            llm_result, error = self._call_llm_with_retry(
                model=self.llm_config.get("model", "gemma:2b-instruct-q4_0"),
                prompt=prompt_retry,
                system=system_message,
                format_json=True,
                max_retries=1,  
            )

            if error:
                if attempt < max_retries:
                    continue
                self.log(f"Content LLM failed: {error.get('error')}", "error")
                break

            score = llm_result.get("content_score", 100)
            for obs in llm_result.get("observations", []):
                issues.append({
                    "type": f"content_{obs.get('type', 'observation')}",
                    "severity": self._normalize_severity(obs.get("severity", "info")),
                    "description": f"Content: {obs.get('description')}",
                    "remediation": obs.get("recommendation"),
                })
            break  

        return AgentResult(
            score=max(0, score),
            issues=issues,
            duration=time.time() - start_time,
            agent_name="Content",
            metadata={"text_length": len(text_content)},
        )


class VisualAgent(BaseAgent):
    """Visual audit agent: Design, UX, layout analysis via VLM.

    Requires browser screenshot and vision model.
    """

    def __init__(
        self,
        config: dict,
        logger: Callable[[str, str], None] | None = None,
    ) -> None:
        super().__init__(config, logger)
        self.visual_config = config
        self.ollama_enabled = llm.is_available()

    def execute(
        self,
        url: str,
        business_name: str,
        bucket: str,
        html_content: str | None = None,
        soup: BeautifulSoup | None = None,
        response: requests.Response | None = None,
        screenshot_base64: str | None = None,
        previous_results: dict[str, AgentResult] | None = None,
    ) -> AgentResult:
        start_time = time.time()
        issues: list[dict[str, Any]] = []
        score = 100

        if not self.ollama_enabled or not self.enabled:
            return AgentResult(
                score=score,
                issues=issues,
                duration=time.time() - start_time,
                agent_name="Visual",
                metadata={"skipped": "LLM disabled or agent disabled"},
            )

        if not screenshot_base64:
            return AgentResult(
                score=score,
                issues=issues,
                duration=time.time() - start_time,
                agent_name="Visual",
                metadata={"skipped": "No screenshot provided"},
            )

        prompt = self.visual_config.get("prompt_template", "").format(
            business_name=business_name,
            bucket=bucket,
        )
        system_message = self.visual_config.get(
            "system_message",
            "You are a visual UX design expert. Output ONLY valid JSON.",
        )

        max_retries = 2

        for attempt in range(max_retries + 1):
            if attempt > 0:
                self.log(f"  Visual audit retry {attempt}/{max_retries}", "warning")

            visual_result, error = self._call_llm_with_retry(
                model=self.visual_config.get("model", "richardyoung/smolvlm2-2.2b-instruct"),
                prompt=prompt,
                system=system_message,
                format_json=True,
                max_retries=1,  
            )

            if error:
                if attempt < max_retries:
                    continue
                self.log(f"Visual LLM failed: {error.get('error')}", "error")
                break

            score = visual_result.get("visual_score", 100)
            for obs in visual_result.get("observations", []):
                issues.append({
                    "type": f"visual_{obs.get('category', 'observation')}",
                    "severity": self._normalize_severity(obs.get("severity", "info")),
                    "description": f"Visual: {obs.get('description')}",
                    "remediation": obs.get("recommendation"),
                })
            break  

        return AgentResult(
            score=max(0, score),
            issues=issues,
            duration=time.time() - start_time,
            agent_name="Visual",
            metadata={"screenshot_size": len(screenshot_base64) if screenshot_base64 else 0},
        )


class BusinessAgent(BaseAgent):
    """Business audit agent: Industry-specific requirements.

    Checks for bucket-specific features (e.g., portfolio for designers,
    GitHub for developers, case studies for agencies).
    """

    def __init__(
        self,
        config: dict,
        logger: Callable[[str, str], None] | None = None,
    ) -> None:
        super().__init__(config, logger)
        self.bucket_overrides = config.get("bucket_overrides", {})
        self.ollama_enabled = llm.is_available()

    def execute(
        self,
        url: str,
        business_name: str,
        bucket: str,
        html_content: str | None = None,
        soup: BeautifulSoup | None = None,
        response: requests.Response | None = None,
        screenshot_base64: str | None = None,
        previous_results: dict[str, AgentResult] | None = None,
    ) -> AgentResult:
        start_time = time.time()
        issues: list[dict[str, Any]] = []
        score = 100

        if not html_content or not soup:
            fetched = self._fetch_url(url)
            if fetched is None:
                return AgentResult(
                    score=0,
                    issues=[{"type": "error", "severity": "critical", "description": "Fetch failed"}],
                    duration=time.time() - start_time,
                    agent_name="Business",
                    metadata={"error": "fetch_failed"},
                )
            html_content, soup, _ = fetched

        bucket_checks = self.bucket_overrides.get(bucket, [])

        for check in bucket_checks:
            check_type = check.get("type")
            severity = self._normalize_severity(check.get("severity", "info"))

            if check_type == "link_match":
                patterns = check.get("patterns", [])
                found = any(
                    pattern.lower() in html_content.lower()
                    for pattern in patterns
                )
                if not found:
                    issues.append({
                        "type": check["id"],
                        "severity": severity,
                        "description": check["description"],
                        "remediation": check.get("remediation"),
                    })
                    score -= check["score_impact"]

            elif check_type == "text_match":
                patterns = check.get("patterns", [])
                found = any(
                    pattern.lower() in html_content.lower()
                    for pattern in patterns
                )
                if not found:
                    issues.append({
                        "type": check["id"],
                        "severity": severity,
                        "description": check["description"],
                        "remediation": check.get("remediation"),
                    })
                    score -= check["score_impact"]

        if self.ollama_enabled and self.config.get("llm_business_audit", {}).get("enabled"):
            llm_config = self.config["llm_business_audit"]
            text_content = soup.get_text(separator=" ", strip=True)[:1000]

            max_retries = 2
            content_lengths = [1000, 500, 200]

            for attempt in range(max_retries + 1):
                current_content_len = content_lengths[min(attempt, len(content_lengths) - 1)]

                prompt_retry = llm_config.get("prompt_template", "").format(
                    business_name=business_name,
                    bucket=bucket,
                    content=text_content[:current_content_len],
                )

                if attempt > 0:
                    self.log(f"  Business audit retry {attempt}/{max_retries} with {current_content_len} chars", "warning")

                llm_result, error = self._call_llm_with_retry(
                    model=llm_config.get("model", "gemma:2b-instruct-q4_0"),
                    prompt=prompt_retry,
                    system=llm_config.get("system_message", "Output ONLY valid JSON."),
                    format_json=True,
                    max_retries=1,  
                )

                if error:
                    if attempt < max_retries:
                        continue
                    self.log(f"Business LLM failed: {error.get('error')}", "error")
                    break

                for obs in llm_result.get("observations", []):
                    issues.append({
                        "type": f"business_{obs.get('type', 'observation')}",
                        "severity": self._normalize_severity(obs.get("severity", "info")),
                        "description": f"Business: {obs.get('description')}",
                        "remediation": obs.get("recommendation"),
                    })
                break  

        return AgentResult(
            score=max(0, score),
            issues=issues,
            duration=time.time() - start_time,
            agent_name="Business",
            metadata={"bucket": bucket, "bucket_checks_run": len(bucket_checks)},
        )


class ContactAgent(BaseAgent):
    """Contact discovery agent: Email, phone, contact form detection."""

    def __init__(
        self,
        config: dict,
        logger: Callable[[str, str], None] | None = None,
    ) -> None:
        super().__init__(config, logger)

    def _validate_email(self, email: str) -> str | None:
        """Validate and normalize email using email-validator library."""
        if not email or len(email) > 254 or "@" not in email:
            return None
        try:
            return validate_email(email, check_deliverability=True).normalized
        except EmailNotValidError:
            return None

    def _find_emails_in_html(self, soup: BeautifulSoup, base_url: str) -> list[str]:
        """Find all valid emails in HTML from mailto links and text content."""
        emails: list[str] = []
        seen: set[str] = set()

        for elem in soup.find_all(True):
            href = elem.get("href", "")
            if href and isinstance(href, str) and "mailto:" in href.lower():
                for e in href.lower().replace("mailto:", "").split(","):
                    normalized = self._validate_email(e.strip())
                    if normalized and normalized not in seen:
                        emails.append(normalized)
                        seen.add(normalized)

            onclick = elem.get("onclick", "")
            if onclick and "mailto:" in str(onclick).lower():
                for match in re.findall(r"mailto:([^\s\'\",;]+)", str(onclick), re.I):
                    normalized = self._validate_email(match.lower().strip())
                    if normalized and normalized not in seen:
                        emails.append(normalized)
                        seen.add(normalized)

        text = soup.get_text(separator=" ", strip=True)
        for pattern in [
            r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
            r"[\(\<\[]([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})[\)\>\]]",
        ]:
            for match in re.findall(pattern, text):
                normalized = self._validate_email(match.lower().strip())
                if normalized and normalized not in seen:
                    emails.append(normalized)
                    seen.add(normalized)

        return emails

    def _find_contact_form_email(
        self, soup: BeautifulSoup, base_url: str
    ) -> tuple[str | None, str | None]:
        """Extract email from contact form action URLs."""
        for form in soup.find_all("form"):
            action = form.get("action", "")
            if not action or not isinstance(action, str):
                continue

            form_url = urljoin(base_url, action) if not action.startswith("http") else action

            if "mailto:" in action.lower():
                email = action.lower().replace("mailto:", "").strip()
                normalized = self._validate_email(email)
                if normalized:
                    return (normalized, form_url)

            parsed = urlparse(form_url)
            for param in ["email", "to", "recipient", "_replyto"]:
                if param in parsed.query:
                    for value in parse_qs(parsed.query).get(param, []):
                        normalized = self._validate_email(value)
                        if normalized:
                            return (normalized, form_url)

        return (None, None)

    def _find_social_links(self, soup: BeautifulSoup) -> dict[str, str]:
        """Extract social media links from HTML."""
        social: dict[str, str] = {}
        domains = {
            "linkedin": "linkedin.com",
            "facebook": "facebook.com",
            "instagram": "instagram.com",
            "twitter": ["twitter.com", "x.com"],
        }

        for link in soup.find_all("a", href=True):
            href = str(link.get("href", ""))
            href_lower = href.lower()
            for platform, domain in domains.items():
                if isinstance(domain, list):
                    if any(d in href_lower for d in domain) and platform not in social:
                        social[platform] = href
                elif isinstance(domain, str) and domain in href_lower and platform not in social:
                    social[platform] = href

        return social

    def _find_contact_page_url(self, soup: BeautifulSoup, base_url: str) -> str | None:
        """Find contact page URL from navigation links."""
        keywords = ["contact", "get-in-touch", "support"]
        for link in soup.find_all("a", href=True):
            href = str(link.get("href", ""))
            if any(k in href.lower() for k in keywords):
                return urljoin(base_url, href) if not href.startswith("http") else href
        return None

    def _find_phone(self, soup: BeautifulSoup) -> str | None:
        """Extract phone number from tel: links."""
        for link in soup.find_all("a", href=True):
            href = str(link.get("href", ""))
            if href.startswith("tel:"):
                return href.replace("tel:", "")
        return None

    def _discover_contact_info(self, html_content: str, base_url: str) -> dict:
        """Discover contact information from website HTML."""
        soup = BeautifulSoup(html_content, "html.parser")

        emails = self._find_emails_in_html(soup, base_url)
        email = emails[0] if emails else None

        form_email, form_url = self._find_contact_form_email(soup, base_url)
        if not email and form_email:
            email = form_email

        return {
            "email": email,
            "social_links": self._find_social_links(soup),
            "contact_form_url": form_url or self._find_contact_page_url(soup, base_url),
            "phone": self._find_phone(soup),
        }

    def execute(
        self,
        url: str,
        business_name: str,
        bucket: str,
        html_content: str | None = None,
        soup: BeautifulSoup | None = None,
        response: requests.Response | None = None,
        screenshot_base64: str | None = None,
        previous_results: dict[str, AgentResult] | None = None,
    ) -> AgentResult:
        start_time = time.time()

        if not html_content:
            fetched = self._fetch_url(url)
            if fetched is None:
                return AgentResult(
                    score=0,
                    issues=[{"type": "error", "severity": "critical", "description": "Fetch failed"}],
                    duration=time.time() - start_time,
                    agent_name="Contact",
                    metadata={"error": "fetch_failed"},
                )
            html_content, soup, _ = fetched

        discovered_info = self._discover_contact_info(html_content, url)

        if not discovered_info["email"] and discovered_info["contact_form_url"]:
            try:
                c_resp = requests.get(
                    discovered_info["contact_form_url"],
                    headers={"User-Agent": "Mozilla/5.0"},
                    timeout=5,
                )
                c_html = c_resp.text
                c_info = self._discover_contact_info(
                    c_html,
                    discovered_info["contact_form_url"],
                )
                if c_info["email"]:
                    discovered_info["email"] = c_info["email"]
                if c_info["phone"] and not discovered_info["phone"]:
                    discovered_info["phone"] = c_info["phone"]
            except Exception:
                pass

        score = 100
        issues = []

        if not discovered_info["email"]:
            score -= 40
            issues.append({
                "type": "missing_email",
                "severity": "warning",
                "description": "No email address found on website",
                "remediation": "Add visible email address or contact form",
            })

        if not discovered_info["phone"]:
            score -= 20
            issues.append({
                "type": "missing_phone",
                "severity": "info",
                "description": "No phone number found",
                "remediation": "Add phone number for better lead conversion",
            })

        if not discovered_info["contact_form_url"]:
            score -= 20
            issues.append({
                "type": "missing_contact_form",
                "severity": "info",
                "description": "No contact form detected",
                "remediation": "Add contact form for easy lead capture",
            })

        return AgentResult(
            score=max(0, score),
            issues=issues,
            duration=time.time() - start_time,
            agent_name="Contact",
            metadata=discovered_info,
        )


AGENT_REGISTRY: dict[str, type[BaseAgent]] = {
    "technical": TechnicalAgent,
    "content": ContentAgent,
    "visual": VisualAgent,
    "business": BusinessAgent,
    "contact": ContactAgent,
}


def get_agent(agent_name: str, config: dict, logger: Callable | None = None) -> BaseAgent:
    """Factory function to create agent instances."""
    agent_class = AGENT_REGISTRY.get(agent_name)
    if not agent_class:
        raise ValueError(f"Unknown agent: {agent_name}. Available: {list(AGENT_REGISTRY.keys())}")
    return agent_class(config, logger=logger)
