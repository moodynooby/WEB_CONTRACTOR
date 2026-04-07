"""Base classes and types for audit agents."""

import json
from abc import ABC, abstractmethod
from typing import Any, TypedDict

import requests
from bs4 import BeautifulSoup

from infra import llm
from infra.logging import get_logger

logger = get_logger(__name__)

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
        """Call LLM with retry logic using truncated content on failures."""
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
        """Call LLM with retry logic for timeouts/invalid JSON."""
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
        """Apply penalties to score based on found issues."""
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
