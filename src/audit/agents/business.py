"""Business audit agent: Industry-specific requirements."""

import time
from typing import Any

from bs4 import BeautifulSoup

from infra import llm
from audit.agents.base import BaseAgent, AgentResult


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
        """Execute business audit."""
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
