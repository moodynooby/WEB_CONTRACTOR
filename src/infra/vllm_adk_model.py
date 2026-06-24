"""vLLM ADK Model Wrapper — makes embedded vLLM work with Google ADK agents.

ADK's LlmAgent expects a model object with a ``generate_content`` method.
This wrapper delegates to the embedded vLLM engine so ADK pipelines
(audit, email generation, etc.) work without external servers.

Usage:
    from infra.vllm_adk_model import VllmAdkModel
    model = VllmAdkModel()
    agent = LlmAgent(model=model, name="...", instruction="...")
"""

from __future__ import annotations

from typing import Any

from google.genai import types

from infra.logging import get_logger
from infra.vllm_engine import get_engine

logger = get_logger(__name__)


class VllmAdkModel:
    """Thin wrapper that exposes vLLM via the interface ADK expects."""

    def __init__(self) -> None:
        self._engine = get_engine()

    def generate_content(
        self,
        *,
        model: str | None = None,
        contents: Any = None,
        config: Any = None,
        **kwargs: Any,
    ) -> Any:
        """ADK-compatible generate_content entry point.

        ADK calls this with ``contents`` as a ``types.Content`` object
        (or a list of them). We extract the text, run vLLM, and return
        a ``types.GenerateContentResponse``-compatible object.
        """
        messages = _extract_messages(contents)
        if not messages:
            messages = [{"role": "user", "content": ""}]

        max_tokens = 2048
        temperature = 0.5
        if config is not None:
            if hasattr(config, "max_output_tokens") and config.max_output_tokens:
                max_tokens = config.max_output_tokens
            if hasattr(config, "temperature") and config.temperature is not None:
                temperature = config.temperature

        response_text = self._engine.generate(
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )

        return _wrap_response(response_text)


def _extract_messages(contents: Any) -> list[dict[str, str]]:
    """Convert ADK Content objects to plain message dicts."""
    messages: list[dict[str, str]] = []

    if contents is None:
        return messages

    content_list = contents if isinstance(contents, list) else [contents]

    for content in content_list:
        if isinstance(content, types.Content):
            role = content.role or "user"
            text_parts = []
            for part in (content.parts or []):
                if hasattr(part, "text") and part.text:
                    text_parts.append(part.text)
            if text_parts:
                messages.append({"role": role, "content": "\n".join(text_parts)})
        elif isinstance(content, dict):
            messages.append(content)
        elif isinstance(content, str):
            messages.append({"role": "user", "content": content})

    return messages


class _VllmResponse:
    """Minimal response wrapper matching types.GenerateContentResponse interface."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.candidates = [_Candidate(text)]
        self.prompt_feedback = None
        self.usage_metadata = None


class _Candidate:
    def __init__(self, text: str) -> None:
        self.content = types.Content(
            role="model",
            parts=[types.Part(text=text)],
        )
        self.finish_reason = "STOP"
        self.index = 0
        self.safety_ratings = None
        self.grounding_metadata = None


class _ContentResponse:
    """Wrapper that mimics GenerateContentResponse for ADK."""

    def __init__(self, text: str) -> None:
        self._text = text

    @property
    def text(self) -> str:
        return self._text

    @property
    def candidates(self) -> list[_Candidate]:
        return [_Candidate(self._text)]

    @property
    def prompt_feedback(self) -> None:
        return None

    @property
    def usage_metadata(self) -> None:
        return None


def _wrap_response(text: str) -> _ContentResponse:
    """Wrap raw text into an ADK-compatible response object."""
    return _ContentResponse(text)
