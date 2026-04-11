"""ADK Runner Utilities — thin wrapper around ADK Runner + session management.

Uses the unified LLM model configuration via ``infra.llm_models.get_llm_model()``.
All LLM calls now route through LiteLLM (100+ providers) instead of the legacy
request-based provider pool.

Usage:
    from google.adk.agents import LlmAgent
    from infra.adk_adapter import create_session_and_runner, run_agent_sync
    from infra.llm_models import get_llm_model

    agent = LlmAgent(name="my_agent", model=get_llm_model(), instruction="...")
    result = run_agent_sync(agent, message="Hello")
"""

import asyncio
from typing import Any

from google.adk.agents.llm_agent import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from infra.logging import get_logger
from infra.llm_models import get_llm_model

logger = get_logger(__name__)

APP_NAME = "web_contractor"
USER_ID = "pipeline_user"


def _get_model():
    """Get the configured LLM model (string or LiteLlm instance)."""
    return get_llm_model()


def create_session_and_runner(
    agent: LlmAgent,
    app_name: str = APP_NAME,
    session_id: str | None = None,
) -> tuple[InMemorySessionService, str, Runner]:
    """Create a session service, session ID, and runner for an agent.

    Args:
        agent: The ADK agent to run.
        app_name: ADK app name for session scoping.
        session_id: Optional session ID (auto-generated if None).

    Returns:
        Tuple of (session_service, session_id, runner).
    """
    import secrets

    session_service = InMemorySessionService()
    sid = session_id or f"session_{agent.name}_{secrets.token_hex(4)}"
    runner = Runner(agent=agent, app_name=app_name, session_service=session_service)
    return session_service, sid, runner


async def _run_agent_async(
    agent: LlmAgent,
    message: str,
    app_name: str = APP_NAME,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Run an ADK agent asynchronously and return results.

    Args:
        agent: The ADK agent to run.
        message: User message to send to the agent.
        app_name: ADK app name for session scoping.
        session_id: Optional session ID.

    Returns:
        Dict with ``response`` (final text) and ``state`` (session state).
    """
    session_service, sid, runner = create_session_and_runner(
        agent, app_name=app_name, session_id=session_id,
    )

    await session_service.create_session(
        app_name=app_name, user_id=USER_ID, session_id=sid,
    )

    user_content = types.Content(
        role="user", parts=[types.Part(text=message)]
    )

    final_response = ""
    async for event in runner.run_async(
        user_id=USER_ID, session_id=sid, new_message=user_content,
    ):
        if event.is_final_response() and event.content and event.content.parts:
            final_response = event.content.parts[0].text or ""

    session = await session_service.get_session(
        app_name=app_name, user_id=USER_ID, session_id=sid,
    )
    state = {}
    if session is not None and session.state:
        state = dict(session.state)

    return {
        "response": final_response,
        "state": state,
        "session_id": sid,
    }


def run_agent_sync(
    agent: LlmAgent,
    message: str,
    app_name: str = APP_NAME,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Synchronous convenience wrapper for :func:`_run_agent_async`."""
    return asyncio.run(_run_agent_async(
        agent=agent, message=message, app_name=app_name, session_id=session_id,
    ))
