"""Audit Module - Handles website auditing separate from email generation.

This module provides the AuditOrchestrator class which runs multi-agent
audits on leads to evaluate their websites and determine qualification.
"""

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from typing import Any, Callable

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

from core.agents import (
    AgentResult,
    BaseAgent,
    get_agent,
)
from core.db_repository import (
    get_pending_audits,
    save_audits_batch,
    update_lead_contact_info,
)
from core.utils import load_json_config


class AuditOrchestrator:
    """
    Orchestrates multi-agent audit pipeline.

    Execution flow:
    1. Technical Agent (fast HTTP checks) → Early exit if critical failures
    2. Contact Agent (discover email/phone) → Skip if no contact info
    3. Content Agent (LLM copy analysis) → Optional based on config
    4. Business Agent (industry checks) → Optional based on bucket
    5. Visual Agent (VLM screenshot) → Only for high-value leads

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
        self._browser = None
        self._context = None
        self._session = None

    def log(self, message: str, style: str = "") -> None:
        """Log message with style."""
        self.logger(message, style)

    @contextmanager
    def managed_session(self):
        """Context manager for shared browser session and HTTP session."""
        try:
            import asyncio

            asyncio.get_event_loop()
        except RuntimeError:
            asyncio.set_event_loop(asyncio.new_event_loop())

        self._session = requests.Session()
        self._session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
        )

        try:
            with sync_playwright() as p:
                self._browser = p.chromium.launch(headless=True)
                self._context = self._browser.new_context()
                try:
                    yield self
                finally:
                    self._context.close()
                    self._browser.close()
        except Exception as e:
            self.log(f"Session error: {e}", "error")
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
        screenshot_base64 = None

        results: dict[str, AgentResult] = {}
        agents_run = []
        all_agents = self._create_agents_for_bucket(lead.get("bucket", "default"))

        stage1_agents = [
            (n, a, e) for n, a, e in all_agents if n in ["technical", "contact"]
        ]
        stage2_agents = [
            (n, a, e) for n, a, e in all_agents if n in ["content", "business"]
        ]
        stage3_agents = [(n, a, e) for n, a, e in all_agents if n in ["visual"]]

        early_exit_triggered = False

        if stage1_agents:
            self.log(
                "  Running Stage 1 agents (Technical + Contact) in parallel...", "info"
            )
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = {
                    executor.submit(
                        self._run_agent_parallel,
                        agent_name,
                        agent,
                        lead,
                        html_content,
                        soup,
                        response,
                        screenshot_base64,
                        results,
                    ): agent_name
                    for agent_name, agent, _ in stage1_agents
                }
                for future in as_completed(futures):
                    agent_name, result = future.result()
                    results[agent_name] = result
                    agents_run.append(agent_name)
                    exit_rules = next(
                        (e for n, _, e in stage1_agents if n == agent_name), {}
                    )
                    self.log(
                        f"  {agent_name.title()} complete: score={result['score']}, {len(result.get('issues', []))} issues, {result['duration']:.2f}s",
                        "success",
                    )
                    if exit_rules and self._should_early_exit(result, exit_rules):
                        self.log("  Early exit triggered after Stage 1", "warning")
                        early_exit_triggered = True
                        break

        if stage2_agents and not early_exit_triggered:
            self.log(
                "  Running Stage 2 agents (Content + Business) in parallel...", "info"
            )
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = {
                    executor.submit(
                        self._run_agent_parallel,
                        agent_name,
                        agent,
                        lead,
                        html_content,
                        soup,
                        response,
                        screenshot_base64,
                        results,
                    ): agent_name
                    for agent_name, agent, _ in stage2_agents
                }
                for future in as_completed(futures):
                    agent_name, result = future.result()
                    results[agent_name] = result
                    agents_run.append(agent_name)
                    exit_rules = next(
                        (e for n, _, e in stage2_agents if n == agent_name), {}
                    )
                    self.log(
                        f"  {agent_name.title()} complete: score={result['score']}, {len(result.get('issues', []))} issues, {result['duration']:.2f}s",
                        "success",
                    )
                    if exit_rules and self._should_early_exit(result, exit_rules):
                        self.log("  Early exit triggered after Stage 2", "warning")
                        early_exit_triggered = True
                        break

        if stage3_agents and not early_exit_triggered:
            for agent_name, agent, exit_rules in stage3_agents:
                self.log(f"  Running {agent_name} agent...", "info")
                if not screenshot_base64:
                    screenshot_base64 = self._take_screenshot(lead["website"])
                result = agent.execute(
                    url=lead["website"],
                    business_name=lead["business_name"],
                    bucket=lead.get("bucket", "default"),
                    html_content=html_content,
                    soup=soup,
                    response=response,
                    screenshot_base64=screenshot_base64,
                    previous_results=results,
                )
                results[agent_name] = result
                agents_run.append(agent_name)
                self.log(
                    f"  {agent_name.title()} complete: score={result['score']}, {len(result.get('issues', []))} issues, {result['duration']:.2f}s",
                    "success",
                )

        weights = self.audit_settings.get("agent_weights", {})
        final_score, all_issues = self._aggregate_results(results, weights)

        discovered_info = {}
        if "contact" in results:
            discovered_info = results["contact"].get("metadata", {})
            if discovered_info.get("email") or discovered_info.get("phone"):
                update_lead_contact_info(lead["id"], discovered_info)

        qual_rules = self.audit_settings.get("qualification_rules", {})
        qualified = self._is_qualified(final_score, all_issues, qual_rules)

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

    def _fetch_page(self, url: str):
        """Fetch a URL using requests (fallback) or Playwright."""
        if not url.startswith("http"):
            url = f"https://{url}"
        try:
            resp = self._session.get(url, timeout=15, verify=False)
            if resp.status_code == 200:
                return resp.text, BeautifulSoup(resp.text, "html.parser"), resp
        except Exception as e:
            self.log(f"Fetch error: {e}", "warning")
        return None

    def _take_screenshot(self, url: str) -> str | None:
        """Take screenshot of URL using Playwright."""
        if not self._context:
            return None
        try:
            page = self._context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=10000)
            screenshot = page.screenshot()
            page.close()
            import base64

            return base64.b64encode(screenshot).decode()
        except Exception as e:
            self.log(f"Screenshot failed: {e}", "warning")
        return None

    def _run_agent_parallel(
        self,
        agent_name,
        agent,
        lead,
        html_content,
        soup,
        response,
        screenshot_base64,
        results,
    ):
        """Run agent in parallel context."""
        result = agent.execute(
            url=lead["website"],
            business_name=lead["business_name"],
            bucket=lead.get("bucket", "default"),
            html_content=html_content,
            soup=soup,
            response=response,
            screenshot_base64=screenshot_base64,
            previous_results=results,
        )
        return agent_name, result

    def _should_early_exit(self, result: AgentResult, exit_rules: dict) -> bool:
        """Check if agent result triggers early exit."""
        min_score = exit_rules.get("min_score", 0)
        if result["score"] < min_score:
            self.log(
                f"  Early exit: {result['agent_name']} score {result['score']} below threshold {min_score}",
                "warning",
            )
            return True

        critical_count = exit_rules.get("max_critical_issues", -1)
        if critical_count >= 0:
            critical_issues = [
                i for i in result.get("issues", []) if i.get("severity") == "critical"
            ]
            if len(critical_issues) > critical_count:
                self.log(
                    f"  Early exit: {len(critical_issues)} critical issues (max: {critical_count})",
                    "warning",
                )
                return True
        return False

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
            "execution_order", ["technical", "contact", "content", "business", "visual"]
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
