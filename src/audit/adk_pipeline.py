"""ADK Pipeline — SequentialAgent chaining discovery → audit → email → send.

This replaces the manual ``run_unified_pipeline()`` in ``app.py`` with an
ADK ``SequentialAgent`` where each stage is an ``LlmAgent`` or workflow
agent.  Data flows between stages via ``output_key`` + ``{key}`` instruction
interpolation in session state.

Usage:
    from audit.adk_pipeline import build_full_pipeline, run_full_pipeline

    pipeline = build_full_pipeline()
    result = run_full_pipeline(limit=20)
"""

import asyncio
from typing import Any, Callable

from google.adk.agents.llm_agent import LlmAgent
from google.adk.agents.sequential_agent import SequentialAgent
from google.adk.agents.loop_agent import LoopAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from audit.adk_agents import _run_adk_session
from infra.adk_tools import (
    fetch_website,
    discover_leads,
    get_pending_audits,
    save_audit_result,
    get_qualified_leads,
    generate_email,
    save_email,
    send_email,
    refine_email,
)
from infra.logging import get_logger
from infra.llm_models import get_llm_model

logger = get_logger(__name__)

APP_NAME = "web_contractor_pipeline"
USER_ID = "pipeline_user"



def create_discovery_agent() -> LlmAgent:
    """Create a fresh LlmAgent instance for lead discovery."""
    return LlmAgent(
        name="discovery_agent",
        model=get_llm_model(),
        instruction="""You are a lead discovery coordinator.

IMPORTANT: You MUST actually call the `discover_leads` tool — do NOT simulate or fake tool responses.

Call the `discover_leads` tool to run the discovery pipeline and find new leads.
The tool will return a summary of how many queries were executed and how many leads were found.
After calling the tool, summarize what it returned.""",
        description="Runs lead discovery via Playwright scraper.",
        tools=[discover_leads],
        output_key="discovery_result",
    )



def _audit_coordinator_instruction() -> str:
    return """You are an audit coordinator.

IMPORTANT RULES:
- You MUST actually call the provided tools — do NOT simulate, fake, or hallucinate tool responses.
- When calling `fetch_website`, you MUST pass the `url` parameter with the lead's website URL.
- When calling `save_audit_result`, you MUST pass the required parameters.
- Wait for the real tool response before proceeding to the next step.

Your workflow:
1. Call the `get_pending_audits` tool to fetch leads that need auditing.
2. For EACH lead returned:
   a. Call `fetch_website` with the lead's website URL (e.g., fetch_website(url="https://example.com")).
   b. Analyze the HTML for: content quality, business strategy fit, technical SEO, and performance indicators.
   c. Score each area (0-100) and list issues with severity (critical/warning/info).
   d. Compute a weighted final score (content: 30%, business: 30%, technical: 25%, performance: 15%).
   e. Apply penalties: critical issue = -35, warning = -15, info = -5.
   f. A lead is QUALIFIED if its score is BELOW 90 (meaning the website has problems).
   g. Call `save_audit_result` to persist the audit result.
3. After auditing all leads, provide a summary of how many leads were audited and qualified.

Be thorough and critical in your analysis."""


def create_audit_agent() -> LlmAgent:
    """Create a fresh LlmAgent instance for audit coordination."""
    return LlmAgent(
        name="audit_agent",
        model=get_llm_model(),
        instruction=_audit_coordinator_instruction(),
        description="Coordinates audit of pending leads: fetches websites, analyzes content/SEO/performance, scores, and qualifies.",
        tools=[get_pending_audits, fetch_website, save_audit_result],
        output_key="audit_result",
    )



def _email_generator_instruction() -> str:
    return """You are an email generation coordinator for B2B cold outreach.

IMPORTANT RULES:
- You MUST actually call the provided tools — do NOT simulate, fake, or hallucinate tool responses.
- Wait for real tool responses before proceeding to the next step.

Your workflow:
1. Call the `get_qualified_leads` tool to fetch leads that passed the audit.
2. For EACH qualified lead:
   a. Extract the critical and warning issues from the audit results.
   b. Call the `generate_email` tool to create a personalized cold email referencing specific audit findings.
   c. Call the `save_email` tool to persist the generated email.
3. After processing all leads, provide a summary of how many emails were generated.

Emails should be short (max 120 words), personalized, and reference specific website issues found during the audit."""


def create_email_generator_agent() -> LlmAgent:
    """Create a fresh LlmAgent instance for email generation."""
    return LlmAgent(
        name="email_generator_agent",
        model=get_llm_model(),
        instruction=_email_generator_instruction(),
        description="Generates personalized cold emails for qualified leads based on audit findings.",
        tools=[get_qualified_leads, generate_email, save_email],
        output_key="email_generation_result",
    )



def _email_reviewer_instruction() -> str:
    return """You are an email quality reviewer.

IMPORTANT: You MUST actually call the `refine_email` tool when needed — do NOT simulate or fake tool responses.

Evaluate the generated email(s) for:
1. Personalization: Does it reference the specific business and their issues?
2. Tone: Professional, not pushy or salesy?
3. Brevity: Under 120 words?
4. Clear CTA: Does it offer a specific next step?
5. No placeholders: All {variables} replaced?

If the email passes ALL criteria, respond with: STOP
If the email fails ANY criteria, respond with specific refinement instructions.

Return ONLY "STOP" or your refinement instructions."""


def create_email_reviewer_agent() -> LlmAgent:
    """Create a fresh LlmAgent instance for email review."""
    return LlmAgent(
        name="email_reviewer_agent",
        model=get_llm_model(),
        instruction=_email_reviewer_instruction(),
        description="Reviews generated emails for quality and signals when refinement is complete.",
        tools=[refine_email],
        output_key="email_review_result",
    )


def build_email_refinement_loop() -> LoopAgent:
    """Build a LoopAgent that generates and refines emails iteratively.

    The loop runs: generate_email → review → refine_email → review → ...
    It stops when the reviewer signals "STOP" or after max_iterations.
    """
    return LoopAgent(
        name="email_refinement_loop",
        sub_agents=[create_email_generator_agent(), create_email_reviewer_agent()],
        description="Iteratively generates and refines cold emails until quality criteria are met.",
        max_iterations=3,
    )



def _email_sender_instruction() -> str:
    return """You are an email sending coordinator.

IMPORTANT: You MUST actually call the `send_email` tool — do NOT simulate or fake tool responses.

Your workflow:
1. Review the generated emails from the previous stage.
2. Call the `send_email` tool to send each approved email.
3. Track which emails were sent successfully and which failed.
4. After sending all emails, provide a summary of how many were sent and how many failed."""


def create_email_sender_agent() -> LlmAgent:
    """Create a fresh LlmAgent instance for email sending."""
    return LlmAgent(
        name="email_sender_agent",
        model=get_llm_model(),
        instruction=_email_sender_instruction(),
        description="Sends approved cold emails via SMTP.",
        tools=[send_email],
        output_key="email_send_result",
    )



def build_full_pipeline(
    include_discovery: bool = False,
    include_refinement_loop: bool = False,
    include_email_send: bool = False,
) -> SequentialAgent:
    """Build the full ADK SequentialAgent pipeline.

    Args:
        include_discovery: If True, prepend the discovery stage.
        include_refinement_loop: If True, use the LoopAgent for email refinement instead of single-pass generation.
        include_email_send: If True, append the email sending stage.

    Returns:
        SequentialAgent ready for execution.
    """
    stages: list = []

    if include_discovery:
        stages.append(create_discovery_agent())

    stages.append(create_audit_agent())

    if include_refinement_loop:
        stages.append(build_email_refinement_loop())
    else:
        stages.append(create_email_generator_agent())

    if include_email_send:
        stages.append(create_email_sender_agent())

    return SequentialAgent(
        name="web_contractor_pipeline",
        sub_agents=stages,
        description="Full lead generation pipeline: discovery → audit → email generation → (optional) sending.",
    )



async def run_pipeline_async(
    limit: int = 20,
    include_discovery: bool = False,
    include_refinement_loop: bool = False,
    include_email_send: bool = False,
    progress_callback: Callable | None = None,
) -> dict[str, Any]:
    """Run the full pipeline asynchronously."""
    agent = build_full_pipeline(
        include_discovery=include_discovery,
        include_refinement_loop=include_refinement_loop,
        include_email_send=include_email_send,
    )

    session_id = f"pipeline_{limit}"
    message = f"Run pipeline with limit={limit}"
    if include_discovery:
        message += ", including discovery"

    state = await _run_pipeline_session(
        agent, message, session_id, progress_callback,
    )

    return {
        "discovery": state.get("discovery_result"),
        "audit": state.get("audit_result"),
        "email_generation": state.get("email_generation_result"),
        "email_review": state.get("email_review_result"),
        "email_send": state.get("email_send_result"),
    }


async def _run_pipeline_session(
    agent, message: str, session_id: str, progress_callback: Callable | None,
) -> dict[str, Any]:
    """Run a pipeline agent session and return state."""
    session_service = InMemorySessionService()
    runner = Runner(agent=agent, app_name=APP_NAME, session_service=session_service)

    await session_service.create_session(
        app_name=APP_NAME, user_id=USER_ID, session_id=session_id,
    )

    user_content = types.Content(role="user", parts=[types.Part(text=message)])
    stage_progress = {"current": 0}

    async for event in runner.run_async(
        user_id=USER_ID, session_id=session_id, new_message=user_content,
    ):
        if event.author and event.is_final_response():
            stage_progress["current"] += 1
            if progress_callback:
                progress_callback(stage_progress["current"], 4, f"Stage complete: {event.author}")

    session = await session_service.get_session(
        app_name=APP_NAME, user_id=USER_ID, session_id=session_id,
    )
    return dict(session.state) if session is not None and session.state else {}


def run_pipeline(
    limit: int = 20,
    include_discovery: bool = False,
    include_refinement_loop: bool = False,
    include_email_send: bool = False,
    progress_callback: Callable | None = None,
) -> dict[str, Any]:
    """Synchronous convenience wrapper for :func:`run_pipeline_async`."""
    return asyncio.run(run_pipeline_async(
        limit=limit,
        include_discovery=include_discovery,
        include_refinement_loop=include_refinement_loop,
        include_email_send=include_email_send,
        progress_callback=progress_callback,
    ))



async def run_audit_pipeline_async(
    limit: int = 20,
    progress_callback: Callable | None = None,
) -> dict[str, Any]:
    """Run only the audit stage of the pipeline."""
    agent = SequentialAgent(
        name="audit_only_pipeline",
        sub_agents=[create_audit_agent()],
        description="Audit-only pipeline.",
    )

    session_id = f"audit_pipeline_{limit}"
    state = await _run_adk_session(
        agent, f"Audit {limit} pending leads", session_id,
    )

    return {"audit": state.get("audit_result")}


def run_audit_pipeline(
    limit: int = 20,
    progress_callback: Callable | None = None,
) -> dict[str, Any]:
    """Synchronous audit-only runner."""
    return asyncio.run(run_audit_pipeline_async(
        limit=limit, progress_callback=progress_callback,
    ))
