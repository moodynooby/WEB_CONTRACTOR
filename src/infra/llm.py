"""LLM Client — LiteLLM-backed with unified provider routing.

Replaces the legacy requests-based provider pool with LiteLLM (included via ADK).
Benefits:
- 100+ providers via OpenAI-compatible API (Groq, OpenRouter, Gemini, Anthropic, Ollama, etc.)
- Built-in retry/fallback via LiteLLM
- No manual rate limiting or HTTP session management
- Single config source (llm section in config_defaults.py)
"""

import json
import time
from typing import Any

import litellm

from infra.logging import get_logger
from infra.llm_models import get_llm_model_string
from infra.settings import GROQ_API_KEY, OPENROUTER_API_KEY

logger = get_logger(__name__)


class LLMError(Exception):
    """Raised on a single LLM API failure."""
    pass


class ProviderError(LLMError):
    """Raised when all providers and retries are exhausted."""
    pass


def generate(
    model: str | None = None,
    prompt: str | None = None,
    system: str | None = None,
    format_json: bool = False,
    timeout: int = 30,
    provider: str | None = None,
    max_retries: int = 3,
    max_tokens: int = 2048,
) -> str:
    """Generate text from LLM using LiteLLM.

    Args:
        model: Model name in LiteLLM format. Overrides config if provided.
        prompt: User prompt.
        system: Optional system message.
        format_json: If True, request JSON output.
        timeout: Request timeout in seconds.
        provider: Unused — model param or config determines provider.
        max_retries: Number of retry attempts on failure.
        max_tokens: Maximum tokens for the response.

    Returns:
        Generated text string.

    Raises:
        ProviderError: All retries exhausted.
    """
    import os
    if GROQ_API_KEY and not os.environ.get("GROQ_API_KEY"):
        os.environ["GROQ_API_KEY"] = GROQ_API_KEY
    if OPENROUTER_API_KEY and not os.environ.get("OPENROUTER_API_KEY"):
        os.environ["OPENROUTER_API_KEY"] = OPENROUTER_API_KEY

    model_str = model or get_llm_model_string()

    messages: list[dict] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt or ""})

    params: dict[str, Any] = {
        "model": model_str,
        "messages": messages,
        "temperature": 0.5,
        "max_tokens": max_tokens,
        "timeout": timeout,
    }

    if format_json:
        params["response_format"] = {"type": "json_object"}

    last_error: Exception | None = None

    for attempt in range(max_retries):
        try:
            response = litellm.completion(**params)

            content = response.choices[0].message.content
            if not content or not content.strip():
                raise LLMError("Empty response from LLM")

            if format_json:
                content = _extract_json(content)

            logger.info(f"LLM success (attempt {attempt + 1}/{max_retries})")
            return content

        except Exception as e:
            last_error = e
            logger.warning(f"LLM attempt {attempt + 1}/{max_retries} failed: {e}")
            if attempt < max_retries - 1:
                wait = 2 ** attempt
                time.sleep(wait)

    raise ProviderError(
        f"LLM failed after {max_retries} attempt(s). Last error: {last_error}"
    )


def _extract_json(text: str) -> str:
    """Extract JSON object/array from text that may contain filler."""
    text = text.strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        start, end = text.find("["), text.rfind("]")
    if start != -1 and end != -1 and end > start:
        return text[start:end + 1]
    return text


def generate_bucket_config(
    business_type: str,
    target_locations: list[str],
    max_queries: int = 10,
    max_results: int = 50,
) -> dict:
    """Generate bucket configuration using LLM."""
    system_message = (
        "You create search bucket configurations for lead generation. Output ONLY JSON."
    )

    prompt = f"""Generate a bucket config for '{business_type}' targeting: {", ".join(target_locations) or "All India"}

Return ONLY JSON:
{{
  "name": "{business_type.lower().replace(" ", "_")}",
  "categories": ["{business_type}", "related category 1", "related category 2"],
  "search_patterns": ["best {{service}} in {{city}}", "top {{service}} near me", "affordable {{service}} {{city}}"],
  "geographic_segments": {json.dumps(target_locations)},
  "intent_profile": "Looking for professional {{service}} in {{location}}",
  "priority": 3,
  "monthly_target": 100,
  "max_queries": {max_queries},
  "max_results": {max_results},
  "daily_email_limit": 50
}}

Notes: replace {{service}} with {business_type} terms, 5-10 patterns, valid JSON only."""

    try:
        response = generate(
            prompt=prompt,
            system=system_message,
            format_json=True,
            timeout=60,
        )
        config = json.loads(response)
    except json.JSONDecodeError as e:
        raise LLMError(f"Failed to parse LLM response as JSON: {e}")
    except LLMError:
        raise
    except Exception as e:
        raise LLMError(f"Bucket generation failed: {e}")

    required = ["name", "categories", "search_patterns", "geographic_segments"]
    missing = [f for f in required if f not in config]
    if missing:
        raise LLMError(f"LLM response missing required fields: {', '.join(missing)}")

    config["name"] = config["name"].lower().replace(" ", "_").replace("-", "_")
    config.setdefault("intent_profile", f"Looking for {business_type} services")
    config.setdefault("priority", 3)
    config.setdefault("monthly_target", 100)
    config.setdefault("max_queries", max_queries)
    config.setdefault("max_results", max_results)
    config.setdefault("daily_email_limit", 50)

    for key in ("priority", "monthly_target", "max_queries", "max_results", "daily_email_limit"):
        config[key] = int(config[key])

    return config
