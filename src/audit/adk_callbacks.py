"""ADK Callback Hooks — agent lifecycle callbacks for logging and Telegram.

These functions conform to ``Agent``'s built-in callback interfaces:
- ``before_agent_callback`` / ``after_agent_callback``:
    ``Callable[[Context], Awaitable[Content | None] | Content | None]``
- ``on_tool_error_callback``:
    ``Callable[[BaseTool, dict, Context, Exception], Awaitable[dict | None] | dict | None]``

Usage:
    from audit.adk_callbacks import on_agent_start, on_agent_end

    agent = Agent(
        name="my_agent",
        before_agent_callback=on_agent_start,
        after_agent_callback=on_agent_end,
    )
"""

from google.adk.agents.context import Context
from google.adk.tools.base_tool import BaseTool
from google.genai.types import Content

from infra.logging import get_logger, get_log_streamer

logger = get_logger(__name__)


def _get_telegram_notifier():
    try:
        from infra.notifications.bot import _notifier
        return _notifier
    except Exception:
        return None


async def on_agent_start(ctx: Context) -> Content | None:
    """Called before an agent begins execution.

    Args:
        ctx: The agent invocation context.

    Returns:
        Optional Content to insert into the agent's message history.
    """
    streamer = get_log_streamer()
    agent_name = ctx.agent_name
    log_msg = f"[ADK] {agent_name}: Starting"
    streamer.publish(log_msg, "INFO")
    logger.info(log_msg)
    return None


async def on_agent_end(ctx: Context) -> Content | None:
    """Called after an agent completes execution.

    Args:
        ctx: The agent invocation context.

    Returns:
        Optional Content to insert into the agent's message history.
    """
    streamer = get_log_streamer()
    agent_name = ctx.agent_name

    response_text = ""
    if ctx.user_content and ctx.user_content.parts:
        response_text = ctx.user_content.parts[0].text or ""

    truncated = response_text[:200] if response_text else ""
    log_msg = f"[ADK] {agent_name}: Complete"
    if truncated:
        log_msg += f" — {truncated}"
    streamer.publish(log_msg, "INFO")
    logger.info(log_msg)

    error_text = (response_text or "").lower()
    if "error" in error_text or "fail" in error_text:
        notifier = _get_telegram_notifier()
        if notifier:
            try:
                notifier.send_message(
                    f"ADK Agent Error\n\nAgent: {agent_name}\nError: {truncated[:300]}"
                )
            except Exception as e:
                logger.debug(f"Telegram notification failed: {e}")

    return None


async def on_tool_error(
    tool: BaseTool,
    args: dict,
    ctx: Context,
    error: Exception,
) -> dict | None:
    """Called when a tool call fails.

    Args:
        tool: The tool that raised the exception.
        args: The arguments passed to the tool.
        ctx: The agent invocation context.
        error: The exception that was raised.

    Returns:
        Optional dict to use as the tool response (None = let ADK handle it).
    """
    streamer = get_log_streamer()
    agent_name = ctx.agent_name
    tool_name = getattr(tool, "name", str(tool))
    log_msg = f"[ADK] {agent_name}: Tool error — {tool_name}: {error}"
    streamer.publish(log_msg, "ERROR")
    logger.error(log_msg)

    notifier = _get_telegram_notifier()
    if notifier:
        try:
            notifier.send_message(
                f"ADK Tool Error\n\nAgent: {agent_name}\nTool: {tool_name}\nError: {str(error)[:300]}"
            )
        except Exception as e:
            logger.debug(f"Telegram notification failed: {e}")

    return None
