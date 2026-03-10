"""Audit Orchestrator

Multi-agent audit pipeline with sequential execution and early exit.
Combines audit + inline email generation in unified pipeline.

Key Features:
- Shared browser session across all leads (1 launch per run)
- HTTP session with connection pooling
- Early exit for unqualified leads (saves 5-10s per lead)
- Inline email generation for qualified leads
- Configurable per bucket (agents, weights, execution order)

Performance: 5-10s per lead vs 15-30s (old batch approach)
"""
from core.utils import load_json_config

import asyncio
import json
import time
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
from core import llm
from core.db_repository import (
    get_pending_audits,
    get_qualified_leads,
    save_audits_batch,
    save_emails_batch,
    update_lead_contact_info,
)

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
        self.logger: Callable[[str, str], None] = logger or (lambda msg, style: print(f"[{style}] {msg}"))
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
        """Context manager for shared browser session and HTTP session.

        Playwright sync API manages its own event loop - just ensure one exists.
        """
        try:
            asyncio.get_event_loop()
        except RuntimeError:
            asyncio.set_event_loop(asyncio.new_event_loop())

        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })

        try:
            with sync_playwright() as p:
                self._browser = p.chromium.launch(headless=True)
                self._context = self._browser.new_context()
                try:
                    yield self
                finally:
                    if self._context:
                        self._context.close()
                    if self._browser:
                        self._browser.close()
                    self._browser = None
                    self._context = None
        finally:
            if self._session:
                self._session.close()
            self._session = None

    def _fetch_page(
        self,
        url: str,
    ) -> tuple[str, BeautifulSoup, requests.Response] | None:
        """Fetch page using shared session."""
        try:
            response = self._session.get(url, timeout=10)
            html_content = response.text
            soup = BeautifulSoup(html_content, "html.parser")
            return html_content, soup, response
        except Exception as e:
            self.log(f"  Failed to fetch {url}: {e}", "error")
            return None

    def _take_screenshot(self, url: str) -> str | None:
        """Take screenshot using shared browser context."""
        if not self._context:
            self.log("  Browser context not available for screenshot", "error")
            return None

        try:
            page = self._context.new_page()
            page.goto(url, wait_until="networkidle", timeout=30000)
            screenshot_bytes = page.screenshot(type="png")
            page.close()
            return screenshot_bytes.hex() if screenshot_bytes else None
        except Exception as e:
            self.log(f"  Failed to take screenshot: {e}", "error")
            return None


    def _should_early_exit(
        self,
        result: AgentResult,
        exit_rules: dict,
    ) -> bool:
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
                i for i in result.get("issues", [])
                if i.get("severity") == "critical"
            ]
            if len(critical_issues) > critical_count:
                self.log(
                    f"  Early exit: {len(critical_issues)} critical issues (max: {critical_count})",
                    "warning",
                )
                return True

        return False

    def _aggregate_results(
        self,
        results: dict[str, AgentResult],
        weights: dict[str, float],
    ) -> tuple[int, list[dict[str, Any]]]:
        """Aggregate agent results into final score and issues."""
        total_score = 0
        total_weight = 0
        all_issues = []

        for agent_name, result in results.items():
            weight = weights.get(agent_name, 1.0)
            total_score += result["score"] * weight
            total_weight += weight
            all_issues.extend(result.get("issues", []))

        final_score = int(total_score / total_weight) if total_weight > 0 else 0
        return final_score, all_issues

    def _is_qualified(
        self,
        score: int,
        issues: list[dict[str, Any]],
        rules: dict,
    ) -> bool:
        """Determine if lead is qualified based on score and issues."""
        score_min = rules.get("target_score_min", 0)
        score_max = rules.get("target_score_max", 84)
        min_issues = rules.get("min_issues_required", 2)

        serious_issues = [
            i for i in issues
            if i.get("severity") in ["warning", "critical"]
        ]

        qualified = (
            score >= score_min
            and score <= score_max
            and len(serious_issues) >= min_issues
        )

        if not qualified:
            reasons = []
            if score < score_min:
                reasons.append(f"score {score} too low")
            if score > score_max:
                reasons.append(f"score {score} too high")
            if len(serious_issues) < min_issues:
                reasons.append(f"only {len(serious_issues)} issues (need {min_issues})")
            self.log(f"  ✗ Not qualified: {', '.join(reasons)}", "warning")

        return qualified

    def _create_agents_for_bucket(
        self,
        bucket: str,
    ) -> list[tuple[str, BaseAgent, dict]]:
        """Create agent instances with bucket-specific config.

        Returns list of (agent_name, agent_instance, exit_rules) tuples.
        """
        agents = []
        execution_order = self.agent_configs.get("execution_order", [
            "technical",
            "contact",
            "content",
            "business",
            "visual",
        ])

        for agent_name in execution_order:
            agent_config = self.agent_configs.get(agent_name, {})

            if not agent_config.get("enabled", True):
                continue

            disabled_buckets = agent_config.get("disabled_for_buckets", [])
            if bucket in disabled_buckets:
                self.log(f"  Skipping {agent_name} agent (disabled for {bucket})", "info")
                continue

            agent = get_agent(agent_name, agent_config, logger=self.logger)
            exit_rules = agent_config.get("early_exit_rules", {})

            agents.append((agent_name, agent, exit_rules))

        return agents

    def audit_lead(
        self,
        lead: dict,
    ) -> dict[str, Any]:
        """Audit single lead using multi-agent pipeline.

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
                "issues": [{"type": "error", "severity": "critical", "description": "Failed to fetch website"}],
                "qualified": 0,
                "discovered_info": {},
                "duration": time.time() - start_time,
                "agents_run": [],
            }

        html_content, soup, response = fetch_result
        screenshot_base64 = None

        results: dict[str, AgentResult] = {}
        agents_run = []
        agents = self._create_agents_for_bucket(lead.get("bucket", "default"))

        for agent_name, agent, exit_rules in agents:
            self.log(f"  Running {agent_name} agent...", "info")

            if agent_name == "visual" and not screenshot_base64:
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
                f"  {agent_name.title()} complete: score={result['score']}, "
                f"{len(result.get('issues', []))} issues, "
                f"{result['duration']:.2f}s",
                "success",
            )

            if exit_rules and self._should_early_exit(result, exit_rules):
                self.log("  Early exit triggered", "warning")
                break

        weights = self.audit_settings.get("agent_weights", {
            "technical": 0.30,
            "content": 0.25,
            "visual": 0.20,
            "business": 0.15,
            "contact": 0.10,
        })

        final_score, all_issues = self._aggregate_results(results, weights)

        discovered_info = {}
        if "contact" in results:
            discovered_info = results["contact"].get("metadata", {})

        qual_rules = self.audit_settings.get("qualification_rules", {})
        qualified = self._is_qualified(final_score, all_issues, qual_rules)

        duration = time.time() - start_time

        self.log(
            f"\n  Final: score={final_score}, qualified={qualified}, "
            f"agents={','.join(agents_run)}, duration={duration:.2f}s",
            "success" if qualified else "warning",
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
            "agent_scores": {name: r["score"] for name, r in results.items()},
        }

    def audit_leads(
        self,
        limit: int = 20,
        progress_callback: Callable[[int, int, str], None] | None = None,
    ) -> dict:
        """Audit pending leads using multi-agent pipeline.

        Args:
            limit: Maximum number of leads to audit
            progress_callback: Optional callback(i, total, message)

        Returns:
            Summary dict with audited, qualified counts
        """
        with self.managed_session():
            self.log(f"\n{'=' * 60}", "info")
            self.log("AUDIT: Multi-Agent Pipeline", "info")
            self.log(f"{'=' * 60}", "info")

            leads = get_pending_audits(limit)
            self.log(f"Auditing {len(leads)} leads...", "info")

            audited = 0
            qualified = 0
            skipped_no_email = 0
            audit_batch = []

            for i, lead in enumerate(leads, 1):
                audit_result = self.audit_lead(lead)

                if audit_result["score"] > 0:
                    audited += 1
                    audit_batch.append({
                        "lead_id": lead["id"],
                        "score": audit_result["score"],
                        "issues_json": json.dumps(audit_result["issues"]),
                        "qualified": audit_result["qualified"],
                        "duration_seconds": audit_result["duration"],
                        "metadata_json": json.dumps({
                            "agents_run": audit_result["agents_run"],
                            "agent_scores": audit_result["agent_scores"],
                        }),
                    })

                    if audit_result["qualified"]:
                        qualified += 1
                        contact_info = audit_result.get("discovered_info", {})
                        if contact_info.get("email"):
                            update_lead_contact_info(
                                lead["id"],
                                {
                                    "email": contact_info["email"],
                                    "phone": contact_info.get("phone"),
                                },
                            )
                            self.log(
                                f"  ✓ Email found: {contact_info['email']}",
                                "success",
                            )
                        else:
                            skipped_no_email += 1
                            self.log(
                                "  ⚠ Qualified but no email found",
                                "warning",
                            )

                if progress_callback:
                    progress_callback(i, len(leads), f"Auditing {lead['business_name']}")

            if audit_batch:
                save_audits_batch(audit_batch)

            self.log(f"\n{'=' * 60}", "info")
            self.log(
                f"Audit Complete: {audited} audited, {qualified} qualified, "
                f"{skipped_no_email} skipped (no email)",
                "success",
            )
            self.log(f"{'=' * 60}\n", "info")

            return {"audited": audited, "qualified": qualified}

    def generate_emails(
        self,
        limit: int = 20,
        progress_callback: Callable[[int, int, str], None] | None = None,
    ) -> dict:
        """Generate emails for qualified leads.
        
        This method generates emails for already-audited qualified leads.
        For unified audit + email generation, use run_unified_pipeline() instead.
        
        Note: This is a simplified implementation. For full email generation,
        use run_unified_pipeline() which handles audit + email in one flow.
        """
        self.log(f"\n{'=' * 60}", "info")
        self.log("EMAIL GENERATION", "info")
        self.log(f"{'=' * 60}", "info")

        leads = get_qualified_leads(limit)
        self.log(f"Generating emails for {len(leads)} qualified leads...", "info")

        generated = 0
        email_batch = []

        for i, lead in enumerate(leads, 1):
            self.log(f"  [{i}/{len(leads)}] {lead['business_name']}", "info")

            audit_result = {
                "issues": json.loads(lead.get("issues_json", "[]")),
            }

            email_start = time.time()
            email_data = self._generate_email_inline(lead, audit_result)

            if email_data:
                email_data["duration"] = time.time() - email_start
                email_batch.append(email_data)
                generated += 1

            if progress_callback:
                progress_callback(i, len(leads), f"Generating for {lead['business_name']}")

        if email_batch:
            save_emails_batch(email_batch)
            self.log(f"  Saved {len(email_batch)} emails", "success")

        self.log(f"\n{'=' * 60}", "info")
        self.log(f"Email Generation Complete: {generated} emails generated", "success")
        self.log(f"{'=' * 60}\n", "info")

        return {"generated": generated}

    def refine_email(
        self,
        subject: str,
        body: str,
        instructions: str,
    ) -> dict[str, str]:
        """Refine an existing email based on user instructions using LLM."""
        email_config = self.audit_settings.get("email_generation", {})
        llm_settings = load_json_config("app_settings.json").get("llm_settings", {})

        if not email_config.get("enabled", True):
            self.log("Email refinement disabled", "warning")
            return {"subject": subject, "body": body}

        prompt = f"""Refine this cold email based on instructions.

Instructions: {instructions}

Current Subject: {subject}
Current Body:
{body}

Return ONLY JSON: {{"subject": "refined subject line", "body": "refined email body"}}"""

        try:
            raw = llm.generate_with_retry(
                model=llm_settings.get("default_model", "gemma:2b-instruct-q4_0"),
                prompt=prompt,
                system="You are a professional email editor. Output ONLY valid JSON.",
                format_json=True,
                max_retries=llm_settings.get("max_retries", 2),
                timeout=llm_settings.get("timeout_seconds", 30),
            )
            data = json.loads(raw)
            return {
                "subject": data.get("subject", subject),
                "body": data.get("body", body),
            }
        except llm.OllamaError as e:
            self.log(f"Email refinement failed: {e}", "error")
            return {"subject": subject, "body": body}

    def _generate_email_inline(
        self,
        lead: dict,
        audit_result: dict,
    ) -> dict | None:
        """Generate email inline using LLM for a qualified lead.

        Args:
            lead: Lead dict with business_name, website, bucket
            audit_result: Audit result dict with issues

        Returns:
            Email dict with subject, body, lead_id, status
        """
        email_config = self.audit_settings.get("email_generation", {})

        if not email_config.get("enabled", True):
            self.log("  ⚠ Email generation disabled, skipping", "warning")
            return None

        issues = audit_result.get("issues", [])
        critical_issues = [i for i in issues if i.get("severity") == "critical"]
        warning_issues = [i for i in issues if i.get("severity") == "warning"]

        top_issues = (critical_issues + warning_issues)[:3]
        issues_text = "\n".join([f"- {i['description']}" for i in top_issues])

        bucket_templates = email_config.get("bucket_templates", {})
        bucket_template = bucket_templates.get(lead.get("bucket", "default"), {})
        angle = bucket_template.get("angle", "")
        cta = bucket_template.get("cta", "")

        prompt = email_config.get("prompt_template", "").format(
            business_name=lead["business_name"],
            bucket=lead.get("bucket", "default"),
            url=lead["website"],
            issues=issues_text,
        )

        if angle:
            prompt += f"\n\nAngle: {angle}"
        if cta:
            prompt += f"\nCTA: {cta}"

        system_message = email_config.get("system_message", "")

        try:
            raw = llm.generate(
                model=email_config.get("model", "gemma:2b-instruct-q4_0"),
                prompt=prompt,
                system=system_message,
                format_json=True,
                timeout=email_config.get("timeout", 30),
            )
            email_data = json.loads(raw)

            signature = email_config.get("signature", {})
            body = email_data.get("body", "")
            if signature.get("closing") and signature["closing"] not in body:
                body += f"\n\n{signature['closing']}\n{signature.get('name', '[Your Name]')}\n{signature.get('company', '')}"

            return {
                "lead_id": lead["id"],
                "subject": email_data.get("subject", f"Quick question for {lead['business_name']}"),
                "body": body,
                "status": "needs_review",  
                "duration": 0,  
            }

        except llm.OllamaError as e:
            self.log(f"  Email generation failed: {e}", "error")
            return None
        except json.JSONDecodeError as e:
            self.log(f"  Failed to parse email JSON: {e}", "error")
            return None

    def run_unified_pipeline(
        self,
        limit: int = 20,
        progress_callback: Callable[[int, int, str], None] | None = None,
    ) -> dict:
        """Run unified audit + email generation pipeline.

        For each lead:
        1. Run multi-agent audit with early exit
        2. If qualified, generate email inline
        3. Save both audit and email to DB
        4. Move to next lead

        Args:
            limit: Maximum number of leads to process
            progress_callback: Optional callback(i, total, message)

        Returns:
            Summary dict with processed, qualified, emails_generated counts
        """
        with self.managed_session():
            self.log("UNIFIED PIPELINE: Audit + Email Generation", "info")

            leads = get_pending_audits(limit)
            self.log(f"Processing {len(leads)} leads...", "info")

            processed = 0
            qualified = 0
            emails_generated = 0
            skipped_no_email = 0
            audit_batch = []
            email_batch = []

            for i, lead in enumerate(leads, 1):
                self.log(f"\n[{i}/{len(leads)}] {lead['business_name']}", "info")

                audit_result = self.audit_lead(lead)

                if audit_result["score"] > 0:
                    processed += 1
                    audit_batch.append({
                        "lead_id": lead["id"],
                        "score": audit_result["score"],
                        "issues_json": json.dumps(audit_result["issues"]),
                        "qualified": audit_result["qualified"],
                        "duration_seconds": audit_result["duration"],
                        "metadata_json": json.dumps({
                            "agents_run": audit_result["agents_run"],
                            "agent_scores": audit_result["agent_scores"],
                        }),
                    })

                    if audit_result["qualified"]:
                        qualified += 1

                        contact_info = audit_result.get("discovered_info", {})
                        if contact_info.get("email"):
                            update_lead_contact_info(
                                lead["id"],
                                {
                                    "email": contact_info["email"],
                                    "phone": contact_info.get("phone"),
                                },
                            )
                            self.log(
                                f"  ✓ Email found: {contact_info['email']}",
                                "success",
                            )

                            self.log("  Generating email...", "info")
                            email_start = time.time()
                            email_data = self._generate_email_inline(lead, audit_result)

                            if email_data:
                                email_data["duration"] = time.time() - email_start
                                email_batch.append(email_data)
                                emails_generated += 1
                                self.log(
                                    f"  ✓ Email generated: {email_data['subject']}",
                                    "success",
                                )
                            else:
                                self.log("  ⚠ Email generation failed", "warning")
                        else:
                            skipped_no_email += 1
                            self.log(
                                "  ⚠ Qualified but no email found - skipping email gen",
                                "warning",
                            )
                    else:
                        self.log("  ✗ Not qualified - skipping email gen", "warning")

                if progress_callback:
                    progress_callback(i, len(leads), f"Processing {lead['business_name']}")

            if audit_batch:
                save_audits_batch(audit_batch)
                self.log(f"  Saved {len(audit_batch)} audits", "success")

            if email_batch:
                save_emails_batch(email_batch)
                self.log(f"  Saved {len(email_batch)} emails", "success")

            self.log(f"\n{'=' * 60}", "info")
            self.log(
                f"Pipeline Complete: {processed} processed, {qualified} qualified, "
                f"{emails_generated} emails generated, {skipped_no_email} skipped (no email)",
                "success",
            )
            self.log(f"{'=' * 60}\n", "info")

            return {
                "processed": processed,
                "qualified": qualified,
                "emails_generated": emails_generated,
                "skipped_no_email": skipped_no_email,
            }
