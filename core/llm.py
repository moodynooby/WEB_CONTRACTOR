"""Ollama Client Module - Thread-safe local LLM calls with rate limiting

Boundaries:
- This module handles ALL Ollama API calls
- External code should NOT make direct requests to Ollama
- Use is_available() to check connectivity
- Use generate() for simple calls (no retry)

Thread Safety:
- Semaphore(1) ensures only 1 concurrent request to local Ollama
- Thread-local sessions prevent shared state issues

Configuration:
- OLLAMA_URL: Set via environment variable (default: http://localhost:11434)
- OLLAMA_TIMEOUT: Default timeout in seconds (default: 30)
"""

import os
import threading
from typing import Any, Dict, Optional

import requests

_semaphore = threading.Semaphore(1)
_local = threading.local()

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
DEFAULT_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "30"))


class OllamaError(Exception):
    """Raised on Ollama failures"""

    pass


def get_session() -> requests.Session:
    """Get thread-local HTTP session"""
    if not hasattr(_local, "session"):
        _local.session = requests.Session()
        _local.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
        )
    return _local.session  # type: ignore[no-any-return]


def is_available() -> bool:
    """Test if Ollama is running"""
    try:
        response = get_session().get(f"{OLLAMA_URL}/api/tags", timeout=5)
        return response.status_code == 200  # type: ignore[no-any-return]
    except requests.exceptions.RequestException:
        return False


def generate(
    model: str,
    prompt: str,
    system: Optional[str] = None,
    format_json: bool = False,
    timeout: int = DEFAULT_TIMEOUT,
) -> str:
    """Generate text from Ollama with rate limiting (no retries)

    Args:
        model: Model name (e.g., "gemma:2b-instruct-q4_0")
        prompt: User prompt (will be compacted to max 1500 chars)
        system: Optional system message (will be compacted to max 100 chars)
        format_json: If True, request JSON output
        timeout: Request timeout in seconds (default: from OLLAMA_TIMEOUT env var)

    Returns:
        Raw response text from model

    Raises:
        OllamaError: On failure
    """
    payload: Dict[str, Any] = {
        "model": model,
        "prompt": _compact_prompt(prompt),
        "stream": False,
    }

    if system:
        payload["system"] = _compact_system(system)

    if format_json:
        payload["format"] = "json"

    with _semaphore:
        try:
            response = get_session().post(
                f"{OLLAMA_URL}/api/generate", json=payload, timeout=timeout
            )

            if response.status_code == 200:
                data = response.json()
                raw = data.get("response", "")
                if not raw or raw.strip() == "":
                    raise OllamaError("Empty response from model")

                if format_json:
                    return _extract_json(raw)
                return raw  # type: ignore[no-any-return]
            else:
                raise OllamaError(f"API error: {response.status_code}")

        except requests.exceptions.Timeout:
            raise OllamaError("Request timeout")
        except requests.exceptions.RequestException as e:
            raise OllamaError(f"Connection error: {e}")


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


def generate_with_retry(
    model: str,
    prompt: str,
    system: Optional[str] = None,
    format_json: bool = False,
    max_retries: int = 3,
    timeout: int = DEFAULT_TIMEOUT,
) -> str:
    """Generate with retry logic (for email operations only)"""
    import time as time_module

    last_error = None

    for attempt in range(max_retries):
        try:
            return generate(model, prompt, system, format_json, timeout)
        except OllamaError as e:
            last_error = e
            if attempt < max_retries - 1:
                time_module.sleep(1)

    raise OllamaError(f"Failed after {max_retries} attempts: {last_error}")


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


def _compact_system(system: str) -> str:
    """Compact system message - keep under 100 chars"""
    compact = system.split(".")[0] if "." in system else system
    if len(compact) > 100:
        compact = compact[:100].strip()
    return compact or "You are a helpful assistant."
