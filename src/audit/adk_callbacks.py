"""ADK Callback Integration — pipes agent events to GUI logs and Telegram.

ADK agents emit lifecycle events (before/after execution, errors).
This module provides callbacks that forward those events to:
1. The GUI log console (via ``infra.logging.LogStreamer``)
2. Telegram notifications (via ``infra.notifications.bot._notifier``)

Usage:
    from audit.adk_callbacks import AdkEventCallback

    callbacks = AdkEventCallback()
    callbacks.on_agent_start("audit_agent")
    # ... run agent ...
    callbacks.on_agent_end("audit_agent", result)
"""

from collections.abc import AsyncGenerator

from google.adk.events import Event

from infra.logging import get_logger, get_log_streamer

logger = get_logger(__name__)


def _get_telegram_notifier():
    """Get the Telegram notifier from the bot module if available."""
    try:
        from infra.notifications.bot import _notifier

        return _notifier
    except Exception:
        return None


class AdkEventCallback:
    """Collects and forwards ADK agent lifecycle events.

    This class provides methods that can be used to intercept ADK events
    and forward them to the existing GUI log streamer and Telegram notifier.
    """

    def __init__(self) -> None:
        self._streamer = get_log_streamer()
        self._logger = get_logger(__name__)

    def on_agent_start(self, agent_name: str, message: str = "") -> None:
        """Called before an agent begins execution.

        Args:
            agent_name: Name of the agent starting.
            message: Optional context message.
        """
        prefix = f"[ADK] {agent_name}"
        log_msg = f"{prefix}: Starting"
        if message:
            log_msg += f" — {message}"
        self._streamer.publish(log_msg, "INFO")
        self._logger.info(log_msg)

    def on_agent_end(self, agent_name: str, result: str = "", duration: float = 0) -> None:
        """Called after an agent completes execution.

        Args:
            agent_name: Name of the agent that finished.
            result: The agent's output (truncated if long).
            duration: Execution time in seconds.
        """
        truncated = result[:200] if result else ""
        log_msg = f"[ADK] {agent_name}: Complete ({duration:.1f}s)"
        if truncated:
            log_msg += f" — {truncated}"
        self._streamer.publish(log_msg, "INFO")
        self._logger.info(log_msg)

    def on_agent_error(self, agent_name: str, error: str = "") -> None:
        """Called when an agent encounters an error.

        Args:
            agent_name: Name of the agent that errored.
            error: Error message.
        """
        log_msg = f"[ADK] {agent_name}: Error — {error}"
        self._streamer.publish(log_msg, "ERROR")
        self._logger.error(log_msg)

        notifier = _get_telegram_notifier()
        if notifier:
            try:
                notifier.send_message(f"🚨 *ADK Agent Error*\n\n*Agent*: {agent_name}\n*Error*: {error[:300]}")
            except Exception as e:
                self._logger.debug(f"Telegram notification failed: {e}")

    def process_event(self, event: Event) -> None:
        """Process a single ADK event and forward to loggers.

        Args:
            event: The ADK event object.
        """
        if event.is_final_response():
            agent_name = event.author or "unknown_agent"
            response_text = ""
            if event.content and event.content.parts:
                response_text = event.content.parts[0].text or ""

            if response_text and ("error" in response_text.lower() or "fail" in response_text.lower()):
                self.on_agent_error(agent_name, response_text[:200])
            else:
                self.on_agent_end(agent_name, response_text)

    async def wrap_pipeline_events(
        self, event_stream: AsyncGenerator[Event, None], pipeline_name: str = "pipeline"
    ) -> AsyncGenerator[Event, None]:
        """Wrap an ADK event stream with logging callbacks.

        Usage:
            async for event in callbacks.wrap_pipeline_events(
                runner.run_async(...), pipeline_name="audit"
            ):
                # process event
                pass

        Args:
            event_stream: The original ADK event stream.
            pipeline_name: Name to use in log messages.

        Yields:
            The same events from the stream, after logging them.
        """
        self.on_agent_start(pipeline_name)
        try:
            async for event in event_stream:
                self.process_event(event)
                yield event
        except Exception as e:
            self.on_agent_error(pipeline_name, str(e))
            raise
        else:
            self.on_agent_end(pipeline_name)
