"""Multi-Agent Audit System

Specialized agents for different audit aspects, configured via config/app_config.json
and executed sequentially with early exit.

Agents:
- ContentAgent: Copy quality, CTAs (LLM-based, 3-5s)
- BusinessAgent: Industry-specific checks (LLM-based, 3-5s)
- TechnicalAgent: SEO, meta tags, structured data (rule-based, <1s)
- PerformanceAgent: Page speed indicators (rule-based, <1s)
"""

import re
import urllib.parse
import json
import time
from abc import ABC, abstractmethod
from typing import Any, TypedDict

import requests
from bs4 import BeautifulSoup, Tag

from core import llm
from core.settings import VERIFY_SSL
from core.logging import get_logger

logger = get_logger(__name__)

DEFAULT_FETCH_TIMEOUT = 10
DEFAULT_LLM_RETRIES = 2
CONTENT_LENGTH_RETRY = [1000, 500, 200]
LLM_TIMEOUT_RETRY = [30, 15, 10]


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
    ) -> None:
        self.config = config
        self.logger = get_logger(self.__class__.__name__)
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
    ) -> AgentResult:
        """Execute the agent's audit logic."""
        pass

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

    def _retry_with_truncated_content(
        self,
        llm_config: dict,
        business_name: str,
        bucket: str,
        text_content: str,
        agent_type: str,
    ) -> tuple[dict, list[dict[str, Any]], int]:
        """Call LLM with retry logic using truncated content on failures.

        Args:
            llm_config: LLM configuration dict
            business_name: Business name for prompt
            bucket: Bucket/category name for prompt
            text_content: Full text content to truncate
            agent_type: Type identifier for logging ("Content" or "Business")

        Returns:
            Tuple of (llm_result, issues, score). On failure, returns ({}, [], 50/70)
        """
        max_retries = DEFAULT_LLM_RETRIES
        content_lengths = CONTENT_LENGTH_RETRY

        for attempt in range(max_retries + 1):
            current_content_len = content_lengths[
                min(attempt, len(content_lengths) - 1)
            ]

            prompt_retry = llm_config.get("prompt_template", "").format(
                business_name=business_name,
                bucket=bucket,
                content=text_content[:current_content_len],
            )

            if attempt > 0:
                self.log(
                    f"  {agent_type} audit retry {attempt}/{max_retries} with {current_content_len} chars",
                    "warning",
                )

            llm_result, error = self._call_llm_with_retry(
                model=llm_config.get("model", "llama-3.1-8b-instant"),
                prompt=prompt_retry,
                system=llm_config.get("system_message", "Output ONLY valid JSON."),
                format_json=True,
                max_retries=1,
            )

            if error:
                if attempt < max_retries:
                    continue
                self.log(f"{agent_type} LLM failed: {error.get('error')}", "error")
                default_score = 50 if agent_type == "Content" else 70
                return {}, [], default_score

            score = llm_result.get(f"{agent_type.lower()}_score", 100)
            issues = []
            for obs in llm_result.get("observations", []):
                issues.append(
                    {
                        "type": f"{agent_type.lower()}_{obs.get('type', 'observation')}",
                        "severity": self._normalize_severity(
                            obs.get("severity", "info")
                        ),
                        "description": f"{agent_type}: {obs.get('description')}",
                        "remediation": obs.get("recommendation"),
                    }
                )
            return llm_result, issues, score

        return {}, [], 50

    def _call_llm_with_retry(
        self,
        model: str,
        prompt: str,
        system: str,
        format_json: bool = True,
        max_retries: int = DEFAULT_LLM_RETRIES,
    ) -> tuple[dict, dict]:
        """Call LLM with retry logic for timeouts/invalid JSON.

        Returns:
            Tuple of (result_dict, error_dict). If successful, error_dict is empty.
        """
        timeouts = LLM_TIMEOUT_RETRY

        for attempt in range(max_retries + 1):
            try:
                current_timeout = timeouts[min(attempt, len(timeouts) - 1)]
                if attempt > 0:
                    self.log(
                        f"  Retry {attempt}/{max_retries} with {current_timeout}s timeout",
                        "warning",
                    )

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

            except llm.ProviderError as e:
                self.log(f"LLM attempt {attempt + 1} failed: {e}", "warning")
                if attempt >= max_retries:
                    return {}, {"error": "llm_error", "message": str(e)}
            except Exception as e:
                self.log(f"LLM unexpected error: {e}", "error")
                if attempt >= max_retries:
                    return {}, {"error": "unexpected", "message": str(e)}

        return {}, {"error": "max_retries_exceeded"}

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

    def _apply_issue_penalties(self, score: int, issues: list[dict[str, Any]]) -> int:
        """Apply penalties to score based on found issues.

        Ensures the final score reflects the severity of detected issues
        even if the LLM provided a generous score.
        """
        if not issues:
            return score

        penalty = 0
        for issue in issues:
            severity = issue.get("severity", "info")
            if severity == "critical":
                penalty += 35
            elif severity == "warning":
                penalty += 15
            else:
                penalty += 5

        return max(0, min(score, 100 - penalty))


class ContentAgent(BaseAgent):
    """Content audit agent: Copy quality, CTAs, value proposition.

    Uses LLM to analyze text content for messaging effectiveness.
    """

    def __init__(
        self,
        config: dict,
    ) -> None:
        super().__init__(config)
        self.llm_config = config
        self.llm_enabled = llm.is_available()

    def execute(
        self,
        url: str,
        business_name: str,
        bucket: str,
        html_content: str | None = None,
        soup: BeautifulSoup | None = None,
    ) -> AgentResult:
        """Execute content audit.

        Args:
            url: Website URL
            business_name: Business name
            bucket: Bucket/category name
            html_content: Raw HTML (required)
            soup: Parsed BeautifulSoup object (optional)

        Returns:
            AgentResult with score, issues, duration, and metadata
        """
        start_time = time.time()
        issues: list[dict[str, Any]] = []
        score = 100

        if not self.llm_enabled or not self.enabled:
            return AgentResult(
                score=score,
                issues=issues,
                duration=time.time() - start_time,
                agent_name="Content",
                metadata={"skipped": "LLM disabled or agent disabled"},
            )

        if not html_content:
            self.log("HTML content required but not provided", "error")
            return AgentResult(
                score=0,
                issues=[
                    {
                        "type": "error",
                        "severity": "critical",
                        "description": "HTML content not provided",
                    }
                ],
                duration=time.time() - start_time,
                agent_name="Content",
                metadata={"error": "missing_html_content"},
            )

        soup_obj = BeautifulSoup(html_content, "html.parser")
        for elem in soup_obj(["script", "style", "meta", "link"]):
            elem.decompose()
        text_content = soup_obj.get_text(separator=" ", strip=True)[:2000]

        llm_result, llm_issues, llm_score = self._retry_with_truncated_content(
            llm_config=self.llm_config,
            business_name=business_name,
            bucket=bucket,
            text_content=text_content,
            agent_type="Content",
        )

        score = llm_score
        issues.extend(llm_issues)

        return AgentResult(
            score=self._apply_issue_penalties(score, issues),
            issues=issues,
            duration=time.time() - start_time,
            agent_name="Content",
            metadata={"text_length": len(text_content)},
        )


class BusinessAgent(BaseAgent):
    """Business audit agent: Industry-specific requirements.

    Checks for bucket-specific features (e.g., portfolio for designers,
    GitHub for developers, case studies for agencies).
    """

    def __init__(
        self,
        config: dict,
    ) -> None:
        super().__init__(config)
        self.bucket_overrides = config.get("bucket_overrides", {})
        self.llm_enabled = llm.is_available()

    def execute(
        self,
        url: str,
        business_name: str,
        bucket: str,
        html_content: str | None = None,
        soup: BeautifulSoup | None = None,
    ) -> AgentResult:
        """Execute business audit.

        Args:
            url: Website URL
            business_name: Business name
            bucket: Bucket/category name
            html_content: Raw HTML (required)
            soup: Parsed BeautifulSoup object (required for bucket checks)

        Returns:
            AgentResult with score, issues, duration, and metadata
        """
        start_time = time.time()
        issues: list[dict[str, Any]] = []
        score = 100

        if not html_content or not soup:
            self.log("HTML content and soup required but not provided", "error")
            return AgentResult(
                score=0,
                issues=[
                    {
                        "type": "error",
                        "severity": "critical",
                        "description": "HTML content not provided",
                    }
                ],
                duration=time.time() - start_time,
                agent_name="Business",
                metadata={"error": "missing_html_content"},
            )

        bucket_checks = self.bucket_overrides.get(bucket, [])

        for check in bucket_checks:
            check_type = check.get("type")
            severity = self._normalize_severity(check.get("severity", "info"))

            if check_type == "link_match":
                patterns = check.get("patterns", [])
                found = any(
                    pattern.lower() in html_content.lower() for pattern in patterns
                )
                if not found:
                    issues.append(
                        {
                            "type": check["id"],
                            "severity": severity,
                            "description": check["description"],
                            "remediation": check.get("remediation"),
                        }
                    )
                    score -= check["score_impact"]

            elif check_type == "text_match":
                patterns = check.get("patterns", [])
                found = any(
                    pattern.lower() in html_content.lower() for pattern in patterns
                )
                if not found:
                    issues.append(
                        {
                            "type": check["id"],
                            "severity": severity,
                            "description": check["description"],
                            "remediation": check.get("remediation"),
                        }
                    )
                    score -= check["score_impact"]

        if self.llm_enabled and self.config.get("llm_audit", {}).get("enabled"):
            llm_config = self.config["llm_audit"]
            text_content = soup.get_text(separator=" ", strip=True)[:1000]

            llm_result, llm_issues, llm_score = self._retry_with_truncated_content(
                llm_config=llm_config,
                business_name=business_name,
                bucket=bucket,
                text_content=text_content,
                agent_type="Business",
            )

            score = min(score, llm_score)
            issues.extend(llm_issues)

        return AgentResult(
            score=self._apply_issue_penalties(score, issues),
            issues=issues,
            duration=time.time() - start_time,
            agent_name="Business",
            metadata={"bucket": bucket, "bucket_checks_run": len(bucket_checks)},
        )


class TechnicalAgent(BaseAgent):
    """Technical SEO audit agent: Meta tags, structured data, technical health.

    Rule-based analysis of HTML for SEO and technical best practices.
    Fast execution (<1s) with no LLM dependency.
    """

    def __init__(
        self,
        config: dict,
    ) -> None:
        super().__init__(config)
        self.checks = config.get("checks", {})

    def execute(
        self,
        url: str,
        html_content: str | None = None,
        soup: BeautifulSoup | None = None,
    ) -> AgentResult:
        """Execute technical SEO audit.

        Args:
            url: Website URL
            html_content: Raw HTML (required)
            soup: Parsed BeautifulSoup object (required)

        Returns:
            AgentResult with score, issues, duration, and metadata
        """
        start_time = time.time()
        issues: list[dict[str, Any]] = []
        score = 100

        if not self.enabled:
            return AgentResult(
                score=score,
                issues=issues,
                duration=time.time() - start_time,
                agent_name="Technical",
                metadata={"skipped": "Agent disabled"},
            )

        if not html_content or not soup:
            self.log("HTML content and soup required but not provided", "error")
            return AgentResult(
                score=0,
                issues=[
                    {
                        "type": "error",
                        "severity": "critical",
                        "description": "HTML content not provided",
                    }
                ],
                duration=time.time() - start_time,
                agent_name="Technical",
                metadata={"error": "missing_html_content"},
            )

        title = soup.find("title")
        if not title or not title.get_text(strip=True):
            issues.append(
                {
                    "type": "seo_title_missing",
                    "severity": "critical",
                    "description": "Missing or empty <title> tag",
                    "remediation": "Add a descriptive <title> tag (50-60 characters) that includes business name and key offerings",
                }
            )
            score -= self.checks.get("title_missing_penalty", 20)
        elif len(title.get_text(strip=True)) > 60:
            issues.append(
                {
                    "type": "seo_title_too_long",
                    "severity": "warning",
                    "description": f"Title tag too long ({len(title.get_text(strip=True))} chars, max 60)",
                    "remediation": "Shorten title to 50-60 characters for optimal search display",
                }
            )
            score -= self.checks.get("title_long_penalty", 5)

        meta_desc = soup.find("meta", attrs={"name": "description"})
        meta_desc_content = (
            str(meta_desc.get("content", "") or "")
            if isinstance(meta_desc, Tag)
            else ""
        )

        if not isinstance(meta_desc, Tag) or not meta_desc_content.strip():
            issues.append(
                {
                    "type": "seo_description_missing",
                    "severity": "warning",
                    "description": "Missing meta description",
                    "remediation": "Add a compelling meta description (150-160 characters) summarizing your business",
                }
            )
            score -= self.checks.get("description_missing_penalty", 15)
        elif len(meta_desc_content) > 160:
            issues.append(
                {
                    "type": "seo_description_too_long",
                    "severity": "info",
                    "description": f"Meta description too long ({len(meta_desc_content)} chars, max 160)",
                    "remediation": "Shorten to 150-160 characters for optimal search display",
                }
            )
            score -= self.checks.get("description_long_penalty", 5)

        og_tags = {
            "og:title": soup.find("meta", property="og:title"),
            "og:description": soup.find("meta", property="og:description"),
            "og:image": soup.find("meta", property="og:image"),
            "og:url": soup.find("meta", property="og:url"),
        }
        missing_og = [tag for tag, elem in og_tags.items() if not elem]
        if len(missing_og) >= 3:
            issues.append(
                {
                    "type": "seo_open_graph_missing",
                    "severity": "warning",
                    "description": f"Missing Open Graph tags for social sharing: {', '.join(missing_og)}",
                    "remediation": "Add Open Graph meta tags to improve social media link previews",
                }
            )
            score -= self.checks.get("og_missing_penalty", 10)
        elif missing_og:
            issues.append(
                {
                    "type": "seo_open_graph_incomplete",
                    "severity": "info",
                    "description": f"Incomplete Open Graph tags: {', '.join(missing_og)}",
                    "remediation": "Add missing Open Graph tags for better social sharing",
                }
            )
            score -= self.checks.get("og_incomplete_penalty", 5)

        viewport = soup.find("meta", attrs={"name": "viewport"})
        if not viewport:
            issues.append(
                {
                    "type": "technical_viewport_missing",
                    "severity": "critical",
                    "description": "Missing viewport meta tag - site may not be mobile-friendly",
                    "remediation": "Add <meta name='viewport' content='width=device-width, initial-scale=1'>",
                }
            )
            score -= self.checks.get("viewport_missing_penalty", 20)

        canonical = soup.find("link", rel="canonical")
        if not canonical:
            issues.append(
                {
                    "type": "seo_canonical_missing",
                    "severity": "info",
                    "description": "Missing canonical URL tag",
                    "remediation": "Add <link rel='canonical'> to prevent duplicate content issues",
                }
            )
            score -= self.checks.get("canonical_missing_penalty", 5)

        structured_data = soup.find("script", type="application/ld+json")
        if not structured_data:
            issues.append(
                {
                    "type": "seo_structured_data_missing",
                    "severity": "warning",
                    "description": "No structured data (Schema.org JSON-LD) found",
                    "remediation": "Add JSON-LD structured data for LocalBusiness, Organization, or relevant schema type",
                }
            )
            score -= self.checks.get("structured_data_missing_penalty", 10)

        if self.checks.get("check_robots_txt", True):
            try:
                parsed = urllib.parse.urlparse(url)
                robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
                robots_resp = requests.get(robots_url, timeout=5, verify=VERIFY_SSL)
                if robots_resp.status_code == 404:
                    issues.append(
                        {
                            "type": "technical_robots_txt_missing",
                            "severity": "info",
                            "description": "No robots.txt file found",
                            "remediation": "Create a robots.txt file to guide search engine crawlers",
                        }
                    )
                    score -= self.checks.get("robots_txt_missing_penalty", 5)
            except Exception as e:
                self.log(f"robots.txt check failed: {e}", "warning")

        h1_tags = soup.find_all("h1")
        if not h1_tags:
            issues.append(
                {
                    "type": "technical_h1_missing",
                    "severity": "warning",
                    "description": "No <h1> heading found",
                    "remediation": "Add a clear <h1> heading that describes the page content",
                }
            )
            score -= self.checks.get("h1_missing_penalty", 10)
        elif len(h1_tags) > 1:
            issues.append(
                {
                    "type": "technical_h1_multiple",
                    "severity": "info",
                    "description": f"Multiple <h1> tags found ({len(h1_tags)})",
                    "remediation": "Use only one <h1> tag per page for better SEO",
                }
            )
            score -= self.checks.get("h1_multiple_penalty", 5)

        images = soup.find_all("img")
        images_without_alt = [img for img in images if not img.get("alt")]
        if images and len(images_without_alt) / len(images) > 0.5:
            issues.append(
                {
                    "type": "technical_alt_text_missing",
                    "severity": "warning",
                    "description": f"{len(images_without_alt)}/{len(images)} images missing alt text",
                    "remediation": "Add descriptive alt text to all images for accessibility and SEO",
                }
            )
            score -= self.checks.get("alt_text_missing_penalty", 10)

        if not url.startswith("https://"):
            issues.append(
                {
                    "type": "technical_https_missing",
                    "severity": "critical",
                    "description": "Website not using HTTPS",
                    "remediation": "Install SSL certificate and migrate to HTTPS for security and SEO",
                }
            )
            score -= self.checks.get("https_missing_penalty", 20)

        return AgentResult(
            score=self._apply_issue_penalties(max(0, score), issues),
            issues=issues,
            duration=time.time() - start_time,
            agent_name="Technical",
            metadata={
                "checks_performed": [
                    "title",
                    "description",
                    "open_graph",
                    "viewport",
                    "canonical",
                    "structured_data",
                    "heading_hierarchy",
                    "alt_text",
                    "https",
                ]
            },
        )


class PerformanceAgent(BaseAgent):
    """Performance audit agent: Page speed indicators.

    Rule-based analysis of HTML for performance best practices.
    Fast execution (<1s) with no LLM dependency.
    """

    def __init__(
        self,
        config: dict,
    ) -> None:
        """Initialize PerformanceAgent."""
        super().__init__(config)
        self.thresholds = config.get("thresholds", {})

    def execute(
        self,
        url: str,
        html_content: str | None = None,
        soup: BeautifulSoup | None = None,
        response: requests.Response | None = None,
    ) -> AgentResult:
        """Execute performance audit.

        Args:
            url: Website URL
            html_content: Raw HTML (required)
            soup: Parsed BeautifulSoup object (required)
            response: HTTP response object (optional, used for response time check)

        Returns:
            AgentResult with score, issues, duration, and metadata
        """
        start_time = time.time()
        issues: list[dict[str, Any]] = []
        score = 100

        if not self.enabled:
            return AgentResult(
                score=score,
                issues=issues,
                duration=time.time() - start_time,
                agent_name="Performance",
                metadata={"skipped": "Agent disabled"},
            )

        if not html_content or not soup:
            self.log("HTML content and soup required but not provided", "error")
            return AgentResult(
                score=0,
                issues=[
                    {
                        "type": "error",
                        "severity": "critical",
                        "description": "HTML content not provided",
                    }
                ],
                duration=time.time() - start_time,
                agent_name="Performance",
                metadata={"error": "missing_html_content"},
            )

        html_size = len(html_content.encode("utf-8"))
        max_html_size = self.thresholds.get("max_html_size_kb", 100) * 1024

        if html_size > max_html_size:
            issues.append(
                {
                    "type": "performance_html_too_large",
                    "severity": "warning",
                    "description": f"HTML size is {html_size // 1024}KB (recommended: <{max_html_size // 1024}KB)",
                    "remediation": "Minify HTML, remove unnecessary whitespace and comments",
                }
            )
            score -= 15

        style_tags = soup.find_all("style")
        inline_css_size = sum(len(style.get_text()) for style in style_tags)
        max_inline_css = self.thresholds.get("max_inline_css_kb", 50) * 1024

        if inline_css_size > max_inline_css:
            issues.append(
                {
                    "type": "performance_inline_css_too_large",
                    "severity": "warning",
                    "description": f"Inline CSS is {inline_css_size // 1024}KB (recommended: <{max_inline_css // 1024}KB)",
                    "remediation": "Move inline CSS to external stylesheet files",
                }
            )
            score -= 10

        script_tags = soup.find_all("script")
        inline_js_scripts = [script for script in script_tags if not script.get("src")]
        inline_js_size = sum(len(script.get_text()) for script in inline_js_scripts)
        max_inline_js = self.thresholds.get("max_inline_js_kb", 50) * 1024

        if inline_js_size > max_inline_js:
            issues.append(
                {
                    "type": "performance_inline_js_too_large",
                    "severity": "warning",
                    "description": f"Inline JavaScript is {inline_js_size // 1024}KB (recommended: <{max_inline_js // 1024}KB)",
                    "remediation": "Move inline JavaScript to external files",
                }
            )
            score -= 10

        css_links = soup.find_all("link", rel="stylesheet")
        js_scripts = soup.find_all("script", src=True)
        images = soup.find_all("img")
        total_resources = len(css_links) + len(js_scripts) + len(images)
        max_resources = self.thresholds.get("max_resources", 50)

        if total_resources > max_resources:
            issues.append(
                {
                    "type": "performance_too_many_resources",
                    "severity": "info",
                    "description": f"Page loads {total_resources} resources (recommended: <{max_resources})",
                    "remediation": "Combine CSS/JS files, use CSS sprites for images, lazy-load non-critical images",
                }
            )
            score -= 10

        head = soup.find("head")
        render_blocking_scripts = []
        if head and hasattr(head, "find_all"):
            for script in head.find_all("script", src=True):
                if not script.get("async") and not script.get("defer"):
                    render_blocking_scripts.append(script.get("src"))

        if render_blocking_scripts:
            issues.append(
                {
                    "type": "performance_render_blocking_scripts",
                    "severity": "warning",
                    "description": f"{len(render_blocking_scripts)} render-blocking JavaScript files in <head>",
                    "remediation": "Add 'async' or 'defer' attributes to script tags, or move scripts to end of <body>",
                }
            )
            score -= 15

        images_without_dims = [
            img for img in images if not (img.get("width") and img.get("height"))
        ]
        if images and len(images_without_dims) / len(images) > 0.3:
            issues.append(
                {
                    "type": "performance_missing_image_dimensions",
                    "severity": "info",
                    "description": f"{len(images_without_dims)}/{len(images)} images missing width/height attributes",
                    "remediation": "Add explicit width and height to images to prevent layout shift",
                }
            )
            score -= 10

        lazy_loaded = sum(
            1
            for img in images
            if img.get("loading") == "lazy" or "lazy" in img.get("class", [])
        )
        if images and lazy_loaded == 0 and len(images) > 5:
            issues.append(
                {
                    "type": "performance_no_lazy_loading",
                    "severity": "info",
                    "description": f"No lazy loading on {len(images)} images",
                    "remediation": "Enable lazy loading for below-the-fold images using loading='lazy'",
                }
            )
            score -= 5

        if html_content:
            whitespace_count = len(re.findall(r"\s+", html_content))
            total_chars = len(html_content)
            whitespace_ratio = whitespace_count / total_chars if total_chars > 0 else 0

            if whitespace_ratio > 0.3:
                issues.append(
                    {
                        "type": "performance_html_not_minified",
                        "severity": "info",
                        "description": "HTML appears unminified (excessive whitespace)",
                        "remediation": "Minify HTML to reduce file size",
                    }
                )
                score -= 5

        if response and hasattr(response, "elapsed"):
            response_time_ms = response.elapsed.total_seconds() * 1000
            max_response_time = self.thresholds.get("max_response_time_ms", 1000)

            if response_time_ms > max_response_time:
                issues.append(
                    {
                        "type": "performance_slow_server_response",
                        "severity": "warning",
                        "description": f"Server response time: {response_time_ms:.0f}ms (recommended: <{max_response_time}ms)",
                        "remediation": "Optimize server-side code, use caching, or upgrade hosting",
                    }
                )
                score -= 15

        return AgentResult(
            score=self._apply_issue_penalties(max(0, score), issues),
            issues=issues,
            duration=time.time() - start_time,
            agent_name="Performance",
            metadata={
                "html_size_kb": html_size // 1024,
                "inline_css_kb": inline_css_size // 1024,
                "inline_js_kb": inline_js_size // 1024,
                "total_resources": total_resources,
                "render_blocking_scripts": len(render_blocking_scripts),
            },
        )


AGENT_REGISTRY: dict[str, type[BaseAgent]] = {
    "content": ContentAgent,
    "business": BusinessAgent,
    "technical": TechnicalAgent,
    "performance": PerformanceAgent,
}


def get_agent(agent_name: str, config: dict) -> BaseAgent:
    """Factory function to create agent instances."""
    agent_class = AGENT_REGISTRY.get(agent_name)
    if not agent_class:
        raise ValueError(
            f"Unknown agent: {agent_name}. Available: {list(AGENT_REGISTRY.keys())}"
        )
    return agent_class(config)
