"""Content audit agent: Copy quality, CTAs, value proposition."""

import time
from typing import Any

import requests
from bs4 import BeautifulSoup

from infra import llm
from audit.agents.base import BaseAgent, AgentResult


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
        self.llm_enabled = llm.is_llm_available()

    def execute(
        self,
        url: str,
        business_name: str = "",
        bucket: str = "",
        html_content: str | None = None,
        soup: BeautifulSoup | None = None,
        response: requests.Response | None = None,
    ) -> AgentResult:
        """Execute content audit."""
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
