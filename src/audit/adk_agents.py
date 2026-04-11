"""ADK Audit Agents — LlmAgent + ParallelAgent definitions for website auditing.

Replaces the old audit/agents/ (BaseAgent, ContentAgent, BusinessAgent,
TechnicalAgent, PerformanceAgent) and audit/orchestrator.py with ADK-native
agents that benefit from built-in retry, JSON mode, tool calling, and
structured session state.

Usage:
    from audit.adk_agents import build_audit_pipeline, run_audit

    pipeline = build_audit_pipeline()
    result = run_audit(pipeline, lead={"business_name": "Foo", "website": "...", "bucket": "Restaurants"})
"""

import asyncio
import json
from typing import Any

from google.adk.agents.llm_agent import LlmAgent
from google.adk.agents.parallel_agent import ParallelAgent
from google.adk.agents.sequential_agent import SequentialAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from infra.adk_tools import fetch_website
from infra.logging import get_logger
from infra.settings import get_section
from infra.llm_models import get_llm_model

logger = get_logger(__name__)

APP_NAME = "web_contractor_audit"
USER_ID = "pipeline_user"


async def _run_adk_session(
    agent,
    message: str,
    session_id: str,
    app_name: str = APP_NAME,
) -> dict[str, Any]:
    """Run an ADK agent in a session and return the session state.

    Args:
        agent: ADK agent (or SequentialAgent/ParallelAgent) to run.
        message: User message to send.
        session_id: Unique session identifier.
        app_name: ADK app name for session scoping.

    Returns:
        Session state dict after agent execution.
    """
    session_service = InMemorySessionService()
    runner = Runner(agent=agent, app_name=app_name, session_service=session_service)

    await session_service.create_session(
        app_name=app_name, user_id=USER_ID, session_id=session_id,
    )

    user_content = types.Content(role="user", parts=[types.Part(text=message)])

    async for _ in runner.run_async(
        user_id=USER_ID, session_id=session_id, new_message=user_content,
    ):
        pass

    session = await session_service.get_session(
        app_name=app_name, user_id=USER_ID, session_id=session_id,
    )
    return dict(session.state) if session is not None and session.state else {}



def _audit_tools() -> list:
    """Tools available to audit agents."""
    return [fetch_website]



def _content_instruction(bucket: str = "", business_name: str = "") -> str:
    agent_config = get_section("agents").get("content", {})
    system_msg = agent_config.get(
        "system_message",
        "You are a BRUTALLY HONEST content auditor. Analyze website copy for "
        "clarity, CTAs, value proposition, and trust signals.",
    )

    bucket_rules = ""
    bucket_overrides = agent_config.get("bucket_overrides", {})
    if bucket and bucket in bucket_overrides:
        checks = bucket_overrides[bucket]
        bucket_rules = (
            f"\n\nAdditionally, check for these bucket-specific requirements "
            f"for '{bucket}':\n"
        )
        for check in checks:
            bucket_rules += (
                f"- {check.get('id', '')}: {check.get('description', '')}\n"
            )

    return f"""{system_msg}

You are auditing the website content for '{business_name}' in the '{bucket or 'general'}' industry.

IMPORTANT: You MUST actually call the `fetch_website` tool with the website URL — do NOT simulate or fake tool responses.
Use: fetch_website(url="https://example.com") to retrieve and analyze the website content.

Evaluate:
1. Value Proposition: Clear within 3 seconds?
2. Call-to-Actions: Visible, specific, and compelling?
3. Professional Tone: Appropriate for industry?
4. Trust Signals: Testimonials, badges, credentials?
5. Content Quality: Well-written, no errors?
{bucket_rules}
Scoring: 100=Perfect, 70=Good, 40=Needs improvement, 10=Terrible.

Return ONLY a JSON object with this exact structure:
{{
  "content_score": <integer 0-100>,
  "observations": [
    {{
      "type": "value_proposition|cta|tone|trust|content_quality",
      "severity": "critical|warning|info",
      "description": "specific finding",
      "recommendation": "how to fix"
    }}
  ]
}}"""


content_agent = LlmAgent(
    name="content_auditor",
    model=get_llm_model(),
    instruction=_content_instruction(),
    description="LLM-driven analysis of website content quality, CTAs, value proposition, and trust signals.",
    tools=_audit_tools(),
    output_key="content_result",
)



def _business_instruction(bucket: str = "", business_name: str = "") -> str:
    agent_config = get_section("agents").get("business", {})
    llm_config = agent_config.get("llm_audit", {})
    system_msg = llm_config.get(
        "system_message",
        "You are a BRUTALLY HONEST business strategy expert.",
    )

    bucket_rules = ""
    bucket_overrides = agent_config.get("bucket_overrides", {})
    if bucket and bucket in bucket_overrides:
        checks = bucket_overrides[bucket]
        bucket_rules = "\n\nBucket-specific checks:\n"
        for check in checks:
            patterns = check.get("patterns", [])
            bucket_rules += (
                f"- Check for: {', '.join(patterns)} — "
                f"If missing: {check.get('description', 'N/A')} "
                f"(severity: {check.get('severity', 'warning')})\n"
            )

    return f"""{system_msg}

You are evaluating the business website for '{business_name}' in the '{bucket or 'general'}' industry.

IMPORTANT: You MUST actually call the `fetch_website` tool with the website URL — do NOT simulate or fake tool responses.
Use: fetch_website(url="https://example.com") to retrieve and analyze the website content.

Check:
1. Service Clarity: What they offer is clear?
2. Target Audience: Clear who they serve?
3. Differentiation: What makes them unique?
4. Industry Standards: Meeting expectations?
{bucket_rules}
Scoring: 100=Perfect, 70=Average, 40=Poor, 10=Terrible. Be critical.

Return ONLY a JSON object with this exact structure:
{{
  "business_score": <integer 0-100>,
  "observations": [
    {{
      "type": "service_clarity|target_audience|differentiation|standards",
      "severity": "critical|warning|info",
      "description": "specific finding",
      "recommendation": "how to fix"
    }}
  ]
}}"""


business_agent = LlmAgent(
    name="business_auditor",
    model=get_llm_model(),
    instruction=_business_instruction(),
    description="Industry-specific business strategy checks with LLM audit.",
    tools=_audit_tools(),
    output_key="business_result",
)



def _technical_instruction(bucket: str = "", business_name: str = "") -> str:
    return f"""You are a technical SEO auditor for the website '{business_name}' ({bucket or 'general'} industry).

IMPORTANT: You MUST actually call the `fetch_website` tool with the website URL — do NOT simulate or fake tool responses.
Use: fetch_website(url="https://example.com") to retrieve the website HTML, then analyze it for:

1. Title tag: Present, reasonable length (50-60 chars)?
2. Meta description: Present, reasonable length (120-160 chars)?
3. Open Graph tags: og:title, og:description, og:image present?
4. Viewport meta tag: Present (mobile-friendly)?
5. Canonical URL: Present?
6. Structured data (JSON-LD): Present and valid?
7. Robots.txt: Referenced or accessible?
8. H1 hierarchy: Exactly one H1, proper hierarchy?
9. Image alt text: All images have descriptive alt text?
10. HTTPS: Site uses HTTPS?

Score penalties:
- Missing title: -20, title too long: -5
- Missing description: -15, description too long: -5
- Missing OG tags: -10, incomplete OG: -5
- Missing viewport: -20
- Missing canonical: -5
- Missing structured data: -10
- Missing robots.txt: -5
- Missing/multiple H1: -10/-5
- Missing alt text: -10
- No HTTPS: -20

Return ONLY a JSON object with this exact structure:
{{
  "technical_score": <integer 0-100>,
  "observations": [
    {{
      "type": "title|meta_description|open_graph|viewport|canonical|structured_data|robots_txt|h1|alt_text|https",
      "severity": "critical|warning|info",
      "description": "specific finding",
      "recommendation": "how to fix"
    }}
  ]
}}"""


technical_agent = LlmAgent(
    name="technical_auditor",
    model=get_llm_model(),
    instruction=_technical_instruction(),
    description="Rule-based SEO analysis: meta tags, structured data, Open Graph, H1 hierarchy, alt text, HTTPS.",
    tools=_audit_tools(),
    output_key="technical_result",
)



def _performance_instruction(bucket: str = "", business_name: str = "") -> str:
    thresholds = get_section("agents").get("performance", {}).get("thresholds", {})
    max_html_kb = thresholds.get("max_html_size_kb", 100)
    max_css_kb = thresholds.get("max_inline_css_kb", 50)
    max_js_kb = thresholds.get("max_inline_js_kb", 50)
    max_resources = thresholds.get("max_resources", 50)

    return f"""You are a website performance auditor for '{business_name}' ({bucket or 'general'} industry).

IMPORTANT: You MUST actually call the `fetch_website` tool with the website URL — do NOT simulate or fake tool responses.
Use: fetch_website(url="https://example.com") to retrieve the website HTML, then analyze it for performance indicators:

1. HTML size: Should be under {max_html_kb}KB
2. Inline CSS size: Should be under {max_css_kb}KB
3. Inline JS size: Should be under {max_js_kb}KB
4. Resource count (scripts, stylesheets, images): Should be under {max_resources}
5. Render-blocking scripts: Flag if present
6. Lazy loading: Check for loading="lazy" on images
7. Whitespace ratio: Flag if excessive (>50% whitespace)

Penalties:
- HTML too large: -15
- Inline CSS too large: -10
- Inline JS too large: -10
- Too many resources: -10
- Render-blocking scripts: -15
- No lazy loading on images: -5
- Excessive whitespace: -5

Return ONLY a JSON object with this exact structure:
{{
  "performance_score": <integer 0-100>,
  "observations": [
    {{
      "type": "html_size|css_size|js_size|resource_count|render_blocking|lazy_loading|whitespace",
      "severity": "critical|warning|info",
      "description": "specific finding",
      "recommendation": "how to fix"
    }}
  ]
}}"""


performance_agent = LlmAgent(
    name="performance_auditor",
    model=get_llm_model(),
    instruction=_performance_instruction(),
    description="Rule-based performance analysis: HTML size, inline CSS/JS, resource count, render-blocking scripts, lazy loading.",
    tools=_audit_tools(),
    output_key="performance_result",
)



class AuditResultAggregator:
    """Merges parallel audit agent results into a final score and issue list.

    This replaces the old ``AuditOrchestrator._aggregate_results()`` method.
    """

    def __init__(self) -> None:
        self.weights = get_section("agents").get("weights", {
            "content": 0.3,
            "business": 0.3,
            "technical": 0.25,
            "performance": 0.15,
        })
        self.qualification_rules = get_section("qualification")

    def aggregate(self, state: dict[str, Any]) -> dict[str, Any]:
        """Aggregate agent results from session state.

        Args:
            state: Session state dict populated by parallel agent output_keys.

        Returns:
            Dict with ``score``, ``issues``, ``qualified``, ``agents_run``.
        """
        total_score = 0.0
        total_weight = 0.0
        all_issues: list[dict] = []
        agents_run: list[str] = []

        agent_key_map = {
            "content_auditor": ("content_result", "content"),
            "business_auditor": ("business_result", "business"),
            "technical_auditor": ("technical_result", "technical"),
            "performance_auditor": ("performance_result", "performance"),
        }

        for agent_name, (key, weight_key) in agent_key_map.items():
            raw = state.get(key)
            if not raw:
                continue

            agents_run.append(agent_name)
            weight = self.weights.get(weight_key, 1.0)

            if isinstance(raw, str):
                try:
                    result = json.loads(raw)
                except json.JSONDecodeError:
                    result = {}
            elif isinstance(raw, dict):
                result = raw
            else:
                result = {}

            score_key = f"{weight_key}_score"
            score = result.get(score_key, 50)
            try:
                score = int(score)
            except (ValueError, TypeError):
                score = 50

            for obs in result.get("observations", []):
                all_issues.append({
                    "type": f"{weight_key}_{obs.get('type', 'observation')}",
                    "severity": self._normalize_severity(obs.get("severity", "info")),
                    "description": obs.get("description", ""),
                    "remediation": obs.get("recommendation", ""),
                })

            if weight > 0:
                total_score += score * weight
                total_weight += weight

        final_score = int(total_score / total_weight) if total_weight > 0 else 0

        final_score = self._apply_penalties(final_score, all_issues)

        score_threshold = self.qualification_rules.get("score_threshold", 90)
        qualified = final_score < score_threshold

        return {
            "score": final_score,
            "issues": all_issues,
            "qualified": qualified,
            "agents_run": agents_run,
        }

    def _normalize_severity(self, severity: str) -> str:
        mapping = {
            "critical": ["critical", "high", "error", "fatal"],
            "warning": ["warning", "medium", "warn"],
        }
        s = str(severity).lower().strip()
        for normalized, values in mapping.items():
            if s in values:
                return normalized
        return "info"

    def _apply_penalties(self, score: int, issues: list[dict]) -> int:
        if not issues:
            return score
        penalty = 0
        for issue in issues:
            sev = issue.get("severity", "info")
            if sev == "critical":
                penalty += 35
            elif sev == "warning":
                penalty += 15
            else:
                penalty += 5
        return max(0, min(score, 100 - penalty))



def build_audit_pipeline() -> ParallelAgent:
    """Build the ADK ParallelAgent that runs all 4 audit agents in parallel.

    Returns:
        ParallelAgent ready to be run via ADK Runner.
    """
    return ParallelAgent(
        name="audit_pipeline",
        sub_agents=[content_agent, business_agent, technical_agent, performance_agent],
        description="Runs all 4 audit agents (content, business, technical, performance) in parallel.",
    )


def build_audit_with_lead(lead: dict) -> SequentialAgent:
    """Build a SequentialAgent that first fetches the lead's website, then runs the audit.

    The first stage (``website_fetcher``) calls ``fetch_website`` and stores
    the HTML in session state.  The second stage (``audit_pipeline``) reads
    it and runs all 4 audit agents.

    Args:
        lead: Dict with ``business_name``, ``website``, ``bucket``.

    Returns:
        SequentialAgent ready for execution.
    """
    business_name = lead.get("business_name", "")
    bucket = lead.get("bucket", "")

    lead_content = LlmAgent(
        name="content_auditor",
        model=get_llm_model(),
        instruction=_content_instruction(bucket, business_name),
        description="Content quality audit.",
        tools=_audit_tools(),
        output_key="content_result",
    )
    lead_business = LlmAgent(
        name="business_auditor",
        model=get_llm_model(),
        instruction=_business_instruction(bucket, business_name),
        description="Business strategy audit.",
        tools=_audit_tools(),
        output_key="business_result",
    )
    lead_technical = LlmAgent(
        name="technical_auditor",
        model=get_llm_model(),
        instruction=_technical_instruction(bucket, business_name),
        description="Technical SEO audit.",
        tools=_audit_tools(),
        output_key="technical_result",
    )
    lead_performance = LlmAgent(
        name="performance_auditor",
        model=get_llm_model(),
        instruction=_performance_instruction(bucket, business_name),
        description="Performance audit.",
        tools=_audit_tools(),
        output_key="performance_result",
    )

    parallel = ParallelAgent(
        name="audit_parallel",
        sub_agents=[lead_content, lead_business, lead_technical, lead_performance],
        description="Run all 4 audit agents in parallel.",
    )

    return SequentialAgent(
        name=f"audit_for_{business_name.replace(' ', '_')}",
        sub_agents=[parallel],
        description=f"Full website audit for {business_name}.",
    )



async def run_audit_for_lead(lead: dict) -> dict[str, Any]:
    """Run the full audit pipeline for a single lead.

    Args:
        lead: Dict with ``id``, ``business_name``, ``website``, ``bucket``.

    Returns:
        Audit result dict with ``score``, ``issues``, ``qualified``, etc.
    """
    agent = build_audit_with_lead(lead)
    session_id = f"audit_{lead.get('id', 'unknown')}"
    state = await _run_adk_session(
        agent,
        f"Audit the website at {lead.get('website', '')}",
        session_id,
    )

    aggregator = AuditResultAggregator()
    result = aggregator.aggregate(state)

    return {
        "lead_id": lead.get("id"),
        "url": lead.get("website", ""),
        "score": result["score"],
        "issues": result["issues"],
        "qualified": 1 if result["qualified"] else 0,
        "duration": 0,  
        "agents_run": result["agents_run"],
    }


def run_audit_sync(lead: dict) -> dict[str, Any]:
    """Synchronous wrapper for :func:`run_audit_for_lead`."""
    return asyncio.run(run_audit_for_lead(lead))
