"""Multi-Agent Audit System

Specialized agents for different audit aspects, configured via audit_settings.json
and executed sequentially with early exit.

Agents:
w- ContentAgent: Copy quality, CTAs (LLM-based, 3-5s)
- BusinessAgent: Industry-specific checks (LLM-based, 3-5s)
- VisualAgent: Design, UX analysis (VLM + screenshot, 5-8s, optional)
"""

import json
import os
import time
from abc import ABC, abstractmethod
from typing import Any, Callable, TypedDict

import requests
from bs4 import BeautifulSoup

from core import llm

VERIFY_SSL = os.getenv("REQUESTS_VERIFY_SSL", "true").lower() != "false"


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
            resp = requests.get(url, headers=headers, timeout=10, verify=VERIFY_SSL)
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
        self.llm_enabled = llm.is_available()

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

        if not self.llm_enabled or not self.enabled:
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
                    issues=[
                        {
                            "type": "error",
                            "severity": "critical",
                            "description": "Fetch failed",
                        }
                    ],
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
            current_content_len = content_lengths[
                min(attempt, len(content_lengths) - 1)
            ]

            prompt_retry = self.llm_config.get("prompt_template", "").format(
                business_name=business_name,
                bucket=bucket,
                content=text_content[:current_content_len],
            )

            if attempt > 0:
                self.log(
                    f"  Content audit retry {attempt}/{max_retries} with {current_content_len} chars",
                    "warning",
                )

            llm_result, error = self._call_llm_with_retry(
                model=self.llm_config.get("model", "llama-3.1-8b-instant"),
                prompt=prompt_retry,
                system=system_message,
                format_json=True,
                max_retries=1,
            )

            if error:
                if attempt < max_retries:
                    continue
                self.log(f"Content LLM failed: {error.get('error')}", "error")
                score = 50  
                break

            score = llm_result.get("content_score", 100)
            for obs in llm_result.get("observations", []):
                issues.append(
                    {
                        "type": f"content_{obs.get('type', 'observation')}",
                        "severity": self._normalize_severity(
                            obs.get("severity", "info")
                        ),
                        "description": f"Content: {obs.get('description')}",
                        "remediation": obs.get("recommendation"),
                    }
                )
            break

        return AgentResult(
            score=self._apply_issue_penalties(score, issues),
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
        self.llm_enabled = llm.is_available()

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

        if not self.llm_enabled or not self.enabled:
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
                model=self.visual_config.get("model", "llama-3.2-90b-vision-preview"),
                prompt=prompt,
                system=system_message,
                format_json=True,
                image_base64=screenshot_base64,
                max_retries=1,
            )

            if error:
                if attempt < max_retries:
                    continue
                self.log(f"Visual LLM failed: {error.get('error')}", "error")
                score = 50  
                break

            score = visual_result.get("visual_score", 100)
            for obs in visual_result.get("observations", []):
                issues.append(
                    {
                        "type": f"visual_{obs.get('category', 'observation')}",
                        "severity": self._normalize_severity(
                            obs.get("severity", "info")
                        ),
                        "description": f"Visual: {obs.get('description')}",
                        "remediation": obs.get("recommendation"),
                    }
                )
            break

        return AgentResult(
            score=self._apply_issue_penalties(score, issues),
            issues=issues,
            duration=time.time() - start_time,
            agent_name="Visual",
            metadata={
                "screenshot_size": len(screenshot_base64) if screenshot_base64 else 0
            },
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
        self.llm_enabled = llm.is_available()

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
                    issues=[
                        {
                            "type": "error",
                            "severity": "critical",
                            "description": "Fetch failed",
                        }
                    ],
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

        if self.llm_enabled and self.config.get("llm_business_audit", {}).get(
            "enabled"
        ):
            llm_config = self.config["llm_business_audit"]
            text_content = soup.get_text(separator=" ", strip=True)[:1000]

            max_retries = 2
            content_lengths = [1000, 500, 200]

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
                        f"  Business audit retry {attempt}/{max_retries} with {current_content_len} chars",
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
                    self.log(f"Business LLM failed: {error.get('error')}", "error")
                    score = min(score, 70)  
                    break

                if "business_score" in llm_result:
                    score = min(score, llm_result["business_score"])

                for obs in llm_result.get("observations", []):
                    issues.append(
                        {
                            "type": f"business_{obs.get('type', 'observation')}",
                            "severity": self._normalize_severity(
                                obs.get("severity", "info")
                            ),
                            "description": f"Business: {obs.get('description')}",
                            "remediation": obs.get("recommendation"),
                        }
                    )
                break

        return AgentResult(
            score=self._apply_issue_penalties(score, issues),
            issues=issues,
            duration=time.time() - start_time,
            agent_name="Business",
            metadata={"bucket": bucket, "bucket_checks_run": len(bucket_checks)},
        )


AGENT_REGISTRY: dict[str, type[BaseAgent]] = {
    "content": ContentAgent,
    "visual": VisualAgent,
    "business": BusinessAgent,
}


def get_agent(
    agent_name: str, config: dict, logger: Callable | None = None
) -> BaseAgent:
    """Factory function to create agent instances."""
    agent_class = AGENT_REGISTRY.get(agent_name)
    if not agent_class:
        raise ValueError(
            f"Unknown agent: {agent_name}. Available: {list(AGENT_REGISTRY.keys())}"
        )
    return agent_class(config, logger=logger)
