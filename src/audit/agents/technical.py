"""Technical SEO audit agent: Meta tags, structured data, technical health."""

import time
import urllib.parse
from typing import Any

import requests
from bs4 import BeautifulSoup, Tag

from infra.settings import VERIFY_SSL
from audit.agents.base import BaseAgent, AgentResult


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
        """Execute technical SEO audit."""
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
