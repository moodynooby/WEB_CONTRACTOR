"""LLM Client Module - Groq + OpenRouter with fallback support

Boundaries:
- This module handles ALL LLM API calls (Groq primary, OpenRouter fallback)
- External code should NOT make direct requests to LLM providers
- Use is_available() to check connectivity
- Use generate() for simple calls (no retry)
- Use generate_with_retry() for critical operations (emails)

Thread Safety:
- Thread-local sessions prevent shared state issues
- Rate limiting handled by provider APIs

Configuration:
- GROQ_API_KEY: Required for Groq (get free at https://console.groq.com)
- OPENROUTER_API_KEY: Optional fallback
- DEFAULT_PROVIDER: "groq" or "openrouter" (default: "groq")
- DEFAULT_MODEL: Model ID for primary provider
- FALLBACK_MODEL: Model ID for fallback provider
"""

import os
import threading
import time

import requests

_local = threading.local()

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
DEFAULT_PROVIDER = os.getenv("DEFAULT_PROVIDER", "groq")
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "llama-3.1-8b-instant")
FALLBACK_MODEL = os.getenv("FALLBACK_MODEL", "google/gemma-2-2b-it:free")
DEFAULT_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "30"))

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

PROVIDERS = {
    "groq": {
        "api_key": GROQ_API_KEY,
        "base_url": GROQ_BASE_URL,
        "default_model": DEFAULT_MODEL,
        "extra_headers": {},
    },
    "openrouter": {
        "api_key": OPENROUTER_API_KEY,
        "base_url": OPENROUTER_BASE_URL,
        "default_model": FALLBACK_MODEL,
        "extra_headers": {
            "HTTP-Referer": "https://github.com/web-contractor",
            "X-Title": "Web Contractor",
        },
    },
}


class LLMError(Exception):
    """Raised on LLM API failures"""

    pass


class ProviderError(LLMError):
    """Raised when all providers fail"""

    pass


def get_session() -> requests.Session:
    """Get thread-local HTTP session"""
    if not hasattr(_local, "session"):
        _local.session = requests.Session()
        _local.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36"
            }
        )
    return _local.session  # type: ignore[no-any-return]


def is_available() -> bool:
    """Test if at least one LLM provider is available"""
    for name, config in PROVIDERS.items():
        if config["api_key"]:
            try:
                session = get_session()
                session.headers.update({"Authorization": f"Bearer {config['api_key']}"})
                response = session.get(f"{config['base_url']}/models", timeout=5)
                if response.status_code == 200:
                    return True
            except requests.exceptions.RequestException:
                pass
    return False


def _build_messages(
    prompt: str | None,
    system: str | None,
    image_base64: str | None,
) -> list[dict]:
    """Build message list for API request."""
    messages: list[dict] = []
    if system:
        messages.append({"role": "system", "content": _compact_system(system)})

    if image_base64 and prompt:
        user_content = [
            {"type": "text", "text": _compact_prompt(prompt)},
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{image_base64}"},
            },
        ]
        messages.append({"role": "user", "content": user_content})
    else:
        messages.append({"role": "user", "content": prompt or ""})

    return messages


def _get_provider_headers(api_key: str, extra_headers: dict) -> dict:
    """Build headers for provider API request."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    headers.update(extra_headers)
    return headers


def _handle_api_response(
    response: requests.Response,
    provider_name: str,
    format_json: bool,
) -> str:
    """Handle API response and extract content."""
    if response.status_code == 200:
        data = response.json()
        content = data["choices"][0]["message"]["content"]
        if not content or content.strip() == "":
            raise LLMError(f"Empty response from {provider_name}")

        if format_json:
            return _extract_json(content)
        return content  # type: ignore[no-any-return]
    elif response.status_code == 429:
        raise LLMError(f"{provider_name} rate limit exceeded")
    else:
        raise LLMError(f"{provider_name} API error: {response.status_code}")


def _generate_with_config(
    model: str,
    prompt: str | None,
    system: str | None,
    format_json: bool,
    timeout: int,
    image_base64: str | None,
    provider_name: str,
    api_key: str,
    base_url: str,
    extra_headers: dict,
) -> str:
    """Generate response using specified provider configuration."""
    session = get_session()
    session.headers.update(_get_provider_headers(api_key, extra_headers))

    messages = _build_messages(prompt, system, image_base64)

    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.1 if format_json else 0.3,
        "max_tokens": 2048,
    }

    if format_json:
        payload["response_format"] = {"type": "json_object"}

    try:
        response = session.post(
            f"{base_url}/chat/completions",
            json=payload,
            timeout=timeout,
        )
        return _handle_api_response(response, provider_name, format_json)

    except requests.exceptions.Timeout:
        raise LLMError(f"{provider_name} request timeout")
    except requests.exceptions.RequestException as e:
        raise LLMError(f"{provider_name} connection error: {e}")


def _get_provider_order(provider: str | None):
    """Get ordered list of (provider_name, model) to try."""
    primary = provider or DEFAULT_PROVIDER
    primary_config = PROVIDERS[primary]
    primary_model = primary_config["default_model"]

    if primary_config["api_key"]:
        yield (primary, primary_model)

    for name, config in PROVIDERS.items():
        if name != primary and config["api_key"]:
            yield (name, config["default_model"])


def generate(
    model: str | None = None,
    prompt: str | None = None,
    system: str | None = None,
    format_json: bool = False,
    timeout: int = DEFAULT_TIMEOUT,
    provider: str | None = None,
    image_base64: str | None = None,
) -> str:
    """Generate text from LLM with automatic provider fallback.

    Args:
        model: Model name (default: from env config)
        prompt: User prompt
        system: Optional system message
        format_json: If True, request JSON output
        timeout: Request timeout in seconds
        provider: Force specific provider ("groq" or "openrouter")
        image_base64: Optional base64 image for vision models

    Returns:
        Raw response text from model

    Raises:
        ProviderError: If all providers fail
    """
    errors: list[str] = []

    for provider_name, provider_model in _get_provider_order(provider):
        config = PROVIDERS[provider_name]
        use_model = model or provider_model

        try:
            return _generate_with_config(
                model=use_model,
                prompt=prompt,
                system=system,
                format_json=format_json,
                timeout=timeout,
                image_base64=image_base64,
                provider_name=provider_name,
                api_key=config["api_key"],
                base_url=config["base_url"],
                extra_headers=config["extra_headers"],
            )
        except LLMError as e:
            errors.append(f"{provider_name}: {e}")
            continue

    raise ProviderError(
        f"All providers failed. Errors: {'; '.join(errors)}. "
        f"Groq key: {'yes' if GROQ_API_KEY else 'no'}, "
        f"OpenRouter key: {'yes' if OPENROUTER_API_KEY else 'no'}"
    )


def generate_with_retry(
    model: str | None = None,
    prompt: str | None = None,
    system: str | None = None,
    format_json: bool = False,
    max_retries: int = 3,
    timeout: int = DEFAULT_TIMEOUT,
    provider: str | None = None,
    image_base64: str | None = None,
) -> str:
    """Generate with retry logic (for email operations).

    Retries with exponential backoff on transient failures and
    exponential timeout increase.
    """
    last_error = None

    for attempt in range(max_retries):
        current_timeout = timeout * (2**attempt)

        try:
            return generate(
                model=model,
                prompt=prompt,
                system=system,
                format_json=format_json,
                timeout=current_timeout,
                provider=provider,
                image_base64=image_base64,
            )
        except LLMError as e:
            last_error = e
            if attempt < max_retries - 1:
                wait_time = 2**attempt
                time.sleep(wait_time)

    raise ProviderError(f"Failed after {max_retries} attempts: {last_error}")


def _extract_json(text: str) -> str:
    """Extract JSON object from text that might contain filler."""
    text = text.strip()
    start = text.find("{")
    end = text.rfind("}")

    if start == -1 or end == -1:
        start = text.find("[")
        end = text.rfind("]")

    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    return text


def _compact_prompt(prompt: str, max_length: int = 1500) -> str:
    """Compact prompt for small models - truncate to essential info."""
    if len(prompt) <= max_length:
        return prompt

    truncated = prompt[:max_length]
    last_period = truncated.rfind(".")
    last_newline = truncated.rfind("\n")
    cutoff = max(last_period, last_newline)

    if cutoff > max_length * 0.8:
        return truncated[: cutoff + 1].strip()
    return truncated.strip()


def _compact_system(system: str, max_length: int = 500) -> str:
    """Compact system message for API calls."""
    if len(system) <= max_length:
        return system
    return system[:max_length].strip()


def get_provider_info() -> dict:
    """Get current provider configuration."""
    return {
        "primary_provider": DEFAULT_PROVIDER,
        "groq_configured": bool(GROQ_API_KEY),
        "openrouter_configured": bool(OPENROUTER_API_KEY),
        "default_model": DEFAULT_MODEL,
        "fallback_model": FALLBACK_MODEL,
    }
