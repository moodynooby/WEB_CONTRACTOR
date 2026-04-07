"""Performance audit agent: Page speed indicators."""

import re
import time
from typing import Any

import requests
from bs4 import BeautifulSoup

from audit.agents.base import BaseAgent, AgentResult


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
        """Execute performance audit."""
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
