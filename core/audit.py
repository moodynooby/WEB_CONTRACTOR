"""Audit Module - Handles website auditing separate from email generation.

This module provides the AuditOrchestrator class which runs multi-agent
audits on leads to evaluate their websites and determine qualification.

Multi-Agent Pipeline:
1. Content Agent (LLM copy analysis)
2. Business Agent (industry checks)
3. Technical Agent (SEO, meta tags, structured data)
4. Performance Agent (page speed indicators)

All agents run in parallel for maximum efficiency.
"""

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from typing import Any, Callable

import requests
from bs4 import BeautifulSoup
from core.email import discover_contact_info
from core.agents import (
    AgentResult,
    BaseAgent,
    get_agent,
    DEFAULT_USER_AGENT,
)
from core.db_repository import (
    get_pending_audits,
    save_audits_batch,
)
from core.utils import load_json_config


class AuditOrchestrator:
    """
    Orchestrates multi-agent audit pipeline.

    Execution flow:
    1. Content Agent (LLM copy analysis)
    2. Business Agent (industry checks)
    3. Technical Agent (SEO, meta tags)
    4. Performance Agent (speed indicators)

    All agents run in parallel for maximum efficiency.
    Scores are weighted and aggregated for final qualification decision.
    """

    def __init__(
        self,
        logger: Callable[[str, str], None] | None = None,
    ) -> None:
        self.logger: Callable[[str, str], None] = logger or (
            lambda msg, style: print(f"[{style}] {msg}")
        )
        self.audit_settings = load_json_config("audit_settings.json")
        self.agent_configs = self.audit_settings.get("agents", {})
        self._session = None

    def log(self, message: str, style: str = "") -> None:
        """Log message with style."""
        self.logger(message, style)

    @contextmanager
    def managed_session(self):
        """Context manager for shared HTTP session."""
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": DEFAULT_USER_AGENT})
        yield self

    def audit_lead(self, lead: dict) -> dict[str, Any]:
        """Audit single lead using multi-agent pipeline with PARALLEL execution.

        Args:
            lead: Lead dict with id, business_name, website, bucket

        Returns:
            Audit result dict with score, issues, qualified, discovered_info
        """
        start_time = time.time()
        self.log(f"\nAuditing: {lead['business_name']} ({lead['website']})", "info")

        fetch_result = self._fetch_page(lead["website"])
        if not fetch_result:
            return {
                "lead_id": lead["id"],
                "url": lead["website"],
                "score": 0,
                "issues": [
                    {
                        "type": "error",
                        "severity": "critical",
                        "description": "Failed to fetch website",
                    }
                ],
                "qualified": 0,
                "discovered_info": {},
                "duration": time.time() - start_time,
                "agents_run": [],
            }

        html_content, soup, response = fetch_result

        discovered_info = discover_contact_info(html_content, lead["website"])

        if not discovered_info.get("email"):
            self.log(f"  ✗ No valid email found for {lead['business_name']}", "warning")
            return {
                "lead_id": lead["id"],
                "url": lead["website"],
                "score": 0,
                "issues": [
                    {
                        "type": "error",
                        "severity": "high",
                        "description": "No contact email found on website",
                    }
                ],
                "qualified": 0,
                "discovered_info": discovered_info,
                "duration": time.time() - start_time,
                "agents_run": [],
            }

        results: dict[str, AgentResult] = {}
        agents_run = []
        all_agents = self._create_agents_for_bucket(lead.get("bucket", "default"))

        if not all_agents:
            return {
                "lead_id": lead["id"],
                "url": lead["website"],
                "score": 0,
                "issues": [],
                "qualified": 0,
                "discovered_info": discovered_info,
                "duration": 0,
                "agents_run": agents_run,
            }

        self.log(f"  Running {len(all_agents)} audit agents in parallel...", "info")
        with ThreadPoolExecutor(max_workers=len(all_agents)) as executor:
            futures = {
                executor.submit(
                    self._run_agent_parallel,
                    agent_name,
                    agent,
                    lead,
                    html_content,
                    soup,
                    response,
                    results,
                ): (agent_name, exit_rules)
                for agent_name, agent, exit_rules in all_agents
            }
            for future in as_completed(futures):
                agent_name, result = future.result()
                _, exit_rules = futures[future]
                results[agent_name] = result
                agents_run.append(agent_name)
                self.log(
                    f"  {agent_name.title()} complete: score={result['score']}, {len(result.get('issues', []))} issues, {result['duration']:.2f}s",
                    "success",
                )

                if exit_rules:
                    min_score = exit_rules.get("min_score", 0)
                    if result["score"] < min_score:
                        self.log(
                            f"  ⚠ Early exit: {agent_name} score {result['score']} below threshold {min_score}",
                            "warning",
                        )
                        break

                    max_critical = exit_rules.get("max_critical_issues", -1)
                    if max_critical >= 0:
                        critical_issues = [
                            i for i in result.get("issues", [])
                            if i.get("severity") == "critical"
                        ]
                        if len(critical_issues) > max_critical:
                            self.log(
                                f"  ⚠ Early exit: {len(critical_issues)} critical issues (max: {max_critical})",
                                "warning",
                            )
                            break

        final_score, all_issues = self._aggregate_results(
            results, self.audit_settings.get("agent_weights", {})
        )
        qualified = self._is_qualified(
            final_score, all_issues, self.audit_settings.get("qualification_rules", {})
        )

        duration = time.time() - start_time
        self.log(
            f"\n  Final: score={final_score}, qualified={qualified}, {len(all_issues)} issues, {duration:.2f}s",
            "info",
        )

        return {
            "lead_id": lead["id"],
            "url": lead["website"],
            "score": final_score,
            "issues": all_issues,
            "qualified": 1 if qualified else 0,
            "discovered_info": discovered_info,
            "duration": duration,
            "agents_run": agents_run,
        }

    def audit_leads(
        self, leads: list[dict], progress_callback: Callable | None = None
    ) -> dict:
        """Audit multiple leads with shared session."""
        self.log(f"\n{'=' * 60}", "info")
        self.log(f"AUDIT: Processing {len(leads)} leads", "info")
        self.log(f"{'=' * 60}\n", "info")

        audited = 0
        qualified = 0
        audit_batch = []

        for i, lead in enumerate(leads, 1):
            try:
                result = self.audit_lead(lead)
                audit_batch.append(
                    {
                        "lead_id": lead["id"],
                        "data": result,
                        "duration": result.get("duration"),
                    }
                )
                audited += 1
                if result.get("qualified"):
                    qualified += 1

                if progress_callback:
                    progress_callback(
                        i, len(leads), f"Audited: {lead['business_name']}"
                    )
            except Exception as e:
                self.log(f"Error auditing lead {lead.get('id')}: {e}", "error")

        if audit_batch:
            save_audits_batch(audit_batch)
            self.log(f"Saved {len(audit_batch)} audits", "success")

        self.log(f"AUDIT COMPLETE: {audited} audited, {qualified} qualified", "success")

        return {"audited": audited, "qualified": qualified}

    def run(self, limit: int = 20, progress_callback: Callable | None = None) -> dict:
        """Run audit on pending leads."""
        self.log(f"\n=== Starting Audit (limit={limit}) ===", "info")
        leads = get_pending_audits(limit)
        self.log(f"Found {len(leads)} pending audits", "info")

        if not leads:
            return {"audited": 0, "qualified": 0}

        with self.managed_session():
            return self.audit_leads(leads, progress_callback)

    def _fetch_page(self, url: str) -> tuple[str, BeautifulSoup, Any] | None:
        """Fetch a URL using requests.

        Args:
            url: URL to fetch

        Returns:
            Tuple of (html_content, soup, response) or None if fetch fails
        """
        if not url.startswith("http"):
            url = f"https://{url}"

        try:
            resp = self._session.get(url, timeout=15)
            if resp.status_code == 200:
                return resp.text, BeautifulSoup(resp.text, "html.parser"), resp
        except Exception as e:
            self.log(f"  Requests failed: {e}", "warning")

        return None

    def _run_agent_parallel(
        self,
        agent_name,
        agent,
        lead,
        html_content,
        soup,
        response,
        results,
    ):
        """Run agent in parallel context."""
        agent_type = type(agent).__name__
        if agent_type in ("TechnicalAgent", "PerformanceAgent"):
            result = agent.execute(
                url=lead["website"],
                html_content=html_content,
                soup=soup,
                response=response if agent_type == "PerformanceAgent" else None,
            )
        else:
            result = agent.execute(
                url=lead["website"],
                business_name=lead["business_name"],
                bucket=lead.get("bucket", "default"),
                html_content=html_content,
                soup=soup,
            )
        return agent_name, result

    def _aggregate_results(
        self, results: dict[str, AgentResult], weights: dict[str, float]
    ) -> tuple[int, list[dict[str, Any]]]:
        """Aggregate agent results into final score and issues."""
        total_score = 0
        total_weight = 0
        all_issues = []

        for agent_name, result in results.items():
            weight = weights.get(agent_name, 1.0)
            all_issues.extend(result.get("issues", []))
            if weight <= 0:
                continue
            total_score += result["score"] * weight
            total_weight += weight

        final_score = int(total_score / total_weight) if total_weight > 0 else 0
        return final_score, all_issues

    def _is_qualified(
        self, score: int, issues: list[dict[str, Any]], rules: dict
    ) -> bool:
        """Determine if lead is qualified based on score threshold."""
        score_threshold = rules.get("score_threshold", 90)
        qualified = score < score_threshold
        if not qualified:
            self.log(
                f"  ✗ Not qualified: score {score} >= {score_threshold} (too good)",
                "warning",
            )
        return qualified

    def _create_agents_for_bucket(
        self, bucket: str
    ) -> list[tuple[str, BaseAgent, dict]]:
        """Create agent instances with bucket-specific config."""
        agents = []
        execution_order = self.agent_configs.get(
            "execution_order", ["content", "business"]
        )

        for agent_name in execution_order:
            agent_config = self.agent_configs.get(agent_name, {})
            if not agent_config.get("enabled", True):
                continue
            disabled_buckets = agent_config.get("disabled_for_buckets", [])
            if bucket in disabled_buckets:
                self.log(
                    f"  Skipping {agent_name} agent (disabled for {bucket})", "info"
                )
                continue

            agent = get_agent(agent_name, agent_config, logger=self.logger)
            exit_rules = agent_config.get("early_exit_rules", {})
            agents.append((agent_name, agent, exit_rules))

        return agents
