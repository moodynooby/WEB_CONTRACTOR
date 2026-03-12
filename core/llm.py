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
        _local.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
    return _local.session  # type: ignore[no-any-return]


def is_available() -> bool:
    """Test if at least one LLM provider is available"""
    if GROQ_API_KEY:
        try:
            session = get_session()
            session.headers.update({"Authorization": f"Bearer {GROQ_API_KEY}"})
            response = session.get(
                f"{GROQ_BASE_URL}/models",
                timeout=5
            )
            if response.status_code == 200:
                return True
        except requests.exceptions.RequestException:
            pass

    if OPENROUTER_API_KEY:
        try:
            session = get_session()
            session.headers.update({"Authorization": f"Bearer {OPENROUTER_API_KEY}"})
            response = session.get(
                f"{OPENROUTER_BASE_URL}/models",
                timeout=5
            )
            if response.status_code == 200:
                return True
        except requests.exceptions.RequestException:
            pass

    return False


def generate(
    model: str | None = None,
    prompt: str | None = None,
    system: str | None = None,
    format_json: bool = False,
    timeout: int = DEFAULT_TIMEOUT,
    provider: str | None = None,
    image_base64: str | None = None,
) -> str:
    """Generate text from LLM with automatic provider fallback

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
    if provider is None:
        provider = DEFAULT_PROVIDER

    if model is None:
        model = DEFAULT_MODEL if provider == "groq" else FALLBACK_MODEL

    try:
        if provider == "groq" and GROQ_API_KEY:
            return _generate_groq(
                model=model,
                prompt=prompt,
                system=system,
                format_json=format_json,
                timeout=timeout,
                image_base64=image_base64,
            )
        elif provider == "openrouter" and OPENROUTER_API_KEY:
            return _generate_openrouter(
                model=model,
                prompt=prompt,
                system=system,
                format_json=format_json,
                timeout=timeout,
                image_base64=image_base64,
            )
        else:
            if provider == "groq" and OPENROUTER_API_KEY:
                return _generate_openrouter(
                    model=FALLBACK_MODEL,
                    prompt=prompt,
                    system=system,
                    format_json=format_json,
                    timeout=timeout,
                    image_base64=image_base64,
                )
            elif provider == "openrouter" and GROQ_API_KEY:
                return _generate_groq(
                    model=DEFAULT_MODEL,
                    prompt=prompt,
                    system=system,
                    format_json=format_json,
                    timeout=timeout,
                    image_base64=image_base64,
                )
    except LLMError:
        pass

    if provider == "groq" and OPENROUTER_API_KEY:
        try:
            return _generate_openrouter(
                model=FALLBACK_MODEL,
                prompt=prompt,
                system=system,
                format_json=format_json,
                timeout=timeout,
                image_base64=image_base64,
            )
        except LLMError:
            pass
    elif provider == "openrouter" and GROQ_API_KEY:
        try:
            return _generate_groq(
                model=DEFAULT_MODEL,
                prompt=prompt,
                system=system,
                format_json=format_json,
                timeout=timeout,
                image_base64=image_base64,
            )
        except LLMError:
            pass

    raise ProviderError(
        f"All providers failed. Groq key: {'yes' if GROQ_API_KEY else 'no'}, "
        f"OpenRouter key: {'yes' if OPENROUTER_API_KEY else 'no'}"
    )


def _generate_groq(
    model: str,
    prompt: str | None,
    system: str | None,
    format_json: bool,
    timeout: int,
    image_base64: str | None,
) -> str:
    """Generate using Groq API"""
    session = get_session()
    session.headers.update({
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    })

    messages: list[dict] = []
    if system:
        messages.append({"role": "system", "content": _compact_system(system)})

    if image_base64 and prompt:
        user_content = [
            {"type": "text", "text": _compact_prompt(prompt)},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_base64}"}},
        ]
        messages.append({"role": "user", "content": user_content})
    else:
        messages.append({"role": "user", "content": prompt or ""})

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
            f"{GROQ_BASE_URL}/chat/completions",
            json=payload,
            timeout=timeout,
        )

        if response.status_code == 200:
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            if not content or content.strip() == "":
                raise LLMError("Empty response from Groq")

            if format_json:
                return _extract_json(content)
            return content  # type: ignore[no-any-return]
        elif response.status_code == 429:
            raise LLMError("Groq rate limit exceeded")
        else:
            raise LLMError(f"Groq API error: {response.status_code}")

    except requests.exceptions.Timeout:
        raise LLMError("Groq request timeout")
    except requests.exceptions.RequestException as e:
        raise LLMError(f"Groq connection error: {e}")


def _generate_openrouter(
    model: str,
    prompt: str | None,
    system: str | None,
    format_json: bool,
    timeout: int,
    image_base64: str | None,
) -> str:
    """Generate using OpenRouter API"""
    session = get_session()
    session.headers.update({
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/web-contractor",
        "X-Title": "Web Contractor",
    })

    messages: list[dict] = []
    if system:
        messages.append({"role": "system", "content": _compact_system(system)})

    if image_base64 and prompt:
        user_content = [
            {"type": "text", "text": _compact_prompt(prompt)},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_base64}"}},
        ]
        messages.append({"role": "user", "content": user_content})
    else:
        messages.append({"role": "user", "content": prompt or ""})

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
            f"{OPENROUTER_BASE_URL}/chat/completions",
            json=payload,
            timeout=timeout,
        )

        if response.status_code == 200:
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            if not content or content.strip() == "":
                raise LLMError("Empty response from OpenRouter")

            if format_json:
                return _extract_json(content)
            return content  # type: ignore[no-any-return]
        elif response.status_code == 429:
            raise LLMError("OpenRouter rate limit exceeded")
        else:
            raise LLMError(f"OpenRouter API error: {response.status_code}")

    except requests.exceptions.Timeout:
        raise LLMError("OpenRouter request timeout")
    except requests.exceptions.RequestException as e:
        raise LLMError(f"OpenRouter connection error: {e}")


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
    """Generate with retry logic (for email operations)

    Retries with exponential backoff on transient failures.
    """
    last_error = None

    for attempt in range(max_retries):
        try:
            return generate(
                model=model,
                prompt=prompt,
                system=system,
                format_json=format_json,
                timeout=timeout,
                provider=provider,
                image_base64=image_base64,
            )
        except LLMError as e:
            last_error = e
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  
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
    """Compact prompt for small models - truncate to essential info"""
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
    """Compact system message for API calls"""
    if len(system) <= max_length:
        return system
    return system[:max_length].strip()


def get_provider_info() -> dict:
    """Get current provider configuration"""
    return {
        "primary_provider": DEFAULT_PROVIDER,
        "groq_configured": bool(GROQ_API_KEY),
        "openrouter_configured": bool(OPENROUTER_API_KEY),
        "default_model": DEFAULT_MODEL,
        "fallback_model": FALLBACK_MODEL,
    }
