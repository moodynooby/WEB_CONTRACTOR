"""LLM Client Module - Groq + OpenRouter with local provider support"""

import json
import threading
import time

import requests

from core.settings import (
    GROQ_API_KEY,
    OPENROUTER_API_KEY,
    DEFAULT_PROVIDER,
    DEFAULT_MODEL,
    FALLBACK_MODEL,
    LLM_TIMEOUT,
    GROQ_BASE_URL,
    OPENROUTER_BASE_URL,
    DEFAULT_USER_AGENT,
    LLM_MODE,
    PERFORMANCE_MODE,
    LOCAL_PROVIDER,
    LOCAL_BASE_URL,
    LOCAL_MODEL,
)
from core.mode_config import get_mode_profile
from core.logging import get_logger

logger = get_logger(__name__)

_local = threading.local()

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
    "local": {
        "api_key": "",  
        "base_url": LOCAL_BASE_URL,
        "default_model": LOCAL_MODEL,
        "extra_headers": {},
    },
}


class LLMError(Exception):
    """Raised on LLM API failures"""

    pass


class ProviderError(LLMError):
    """Raised when all providers fail"""

    pass


def get_session() -> requests.Session:
    """Get thread-local HTTP session."""
    if not hasattr(_local, "session"):
        _local.session = requests.Session()
        _local.session.headers.update({"User-Agent": DEFAULT_USER_AGENT})
    return _local.session


def is_available() -> bool:
    """Test if at least one LLM provider is available"""
    if LLM_MODE == "local":
        try:
            session = get_session()
            response = session.get(f"{LOCAL_BASE_URL}", timeout=5)
            if response.status_code == 200:
                return True
        except requests.exceptions.RequestException:
            pass
        return False
    
    for name, config in PROVIDERS.items():
        if name == "local":
            continue  
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
) -> list[dict]:
    """Build message list for API request."""
    messages: list[dict] = []
    if system:
        messages.append({"role": "system", "content": _compact_system(system)})

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
    provider_name: str,
    api_key: str,
    base_url: str,
    extra_headers: dict,
) -> str:
    """Generate response using specified provider configuration."""
    session = get_session()
    session.headers.update(_get_provider_headers(api_key, extra_headers))

    messages = _build_messages(prompt, system)

    mode_profile = get_mode_profile(PERFORMANCE_MODE)
    temperature = mode_profile.get("temperature", 0.1 if format_json else 0.3)
    max_tokens = mode_profile.get("max_tokens", 2048)
    
    timeout_multiplier = mode_profile.get("timeout_multiplier", 1.0)
    adjusted_timeout = int(timeout * timeout_multiplier)

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    if format_json:
        payload["response_format"] = {"type": "json_object"}

    try:
        response = session.post(
            f"{base_url}/chat/completions",
            json=payload,
            timeout=adjusted_timeout,
        )
        return _handle_api_response(response, provider_name, format_json)

    except requests.exceptions.Timeout:
        raise LLMError(f"{provider_name} request timeout")
    except requests.exceptions.RequestException as e:
        raise LLMError(f"{provider_name} connection error: {e}")


def _get_provider_order(provider: str | None):
    """Get ordered list of (provider_name, model) to try."""
    if provider:
        if provider in PROVIDERS:
            config = PROVIDERS[provider]
            yield (provider, config["default_model"])
            return
    
    if LLM_MODE == "local":
        if LOCAL_BASE_URL:
            yield ("local", LOCAL_MODEL)
    else:
        primary = provider or DEFAULT_PROVIDER
        if primary in PROVIDERS and primary != "local":
            primary_config = PROVIDERS[primary]
            if primary_config["api_key"]:
                yield (primary, primary_config["default_model"])

        for name, config in PROVIDERS.items():
            if name != primary and name != "local" and config["api_key"]:
                yield (name, config["default_model"])


def generate(
    model: str | None = None,
    prompt: str | None = None,
    system: str | None = None,
    format_json: bool = False,
    timeout: int = LLM_TIMEOUT,
    provider: str | None = None,
) -> str:
    """Generate text from LLM with automatic provider fallback.

    Args:
        model: Model name (default: from env config)
        prompt: User prompt
        system: Optional system message
        format_json: If True, request JSON output
        timeout: Request timeout in seconds
        provider: Force specific provider ("groq" or "openrouter")

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
        f"Mode: {LLM_MODE}, Performance: {PERFORMANCE_MODE}"
    )


def generate_with_retry(
    model: str | None = None,
    prompt: str | None = None,
    system: str | None = None,
    format_json: bool = False,
    max_retries: int = 3,
    timeout: int = LLM_TIMEOUT,
    provider: str | None = None,
) -> str:
    """Generate with retry logic (for email operations).

    Retries with exponential backoff on transient failures and
    exponential timeout increase. Rate limits get longer backoff.
    """
    import random

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
            )
        except LLMError as e:
            last_error = e
            if attempt < max_retries - 1:
                is_rate_limit = "rate limit" in str(e).lower()
                base_wait = 4 if is_rate_limit else 2
                jitter = random.uniform(0, 1)
                wait_time = (base_wait**attempt) + jitter
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
    info = {
        "mode": LLM_MODE,
        "performance_mode": PERFORMANCE_MODE,
        "primary_provider": DEFAULT_PROVIDER if LLM_MODE == "cloud" else LOCAL_PROVIDER,
        "groq_configured": bool(GROQ_API_KEY),
        "openrouter_configured": bool(OPENROUTER_API_KEY),
        "default_model": DEFAULT_MODEL if LLM_MODE == "cloud" else LOCAL_MODEL,
        "fallback_model": FALLBACK_MODEL,
    }

    if LLM_MODE == "local":
        info["local_provider"] = LOCAL_PROVIDER
        info["local_base_url"] = LOCAL_BASE_URL
        info["local_model"] = LOCAL_MODEL

    return info


def generate_bucket_config(
    business_type: str,
    target_locations: list[str],
    max_queries: int = 10,
    max_results: int = 50,
) -> dict:
    """Generate bucket configuration using LLM.

    Args:
        business_type: Type of business (e.g., "dentists", "yoga studios")
        target_locations: List of target cities/regions
        max_queries: Maximum queries per run (default: 10)
        max_results: Maximum results per query (default: 50)

    Returns:
        Dictionary with bucket configuration including:
        - name: Bucket name
        - categories: List of business categories
        - search_patterns: List of search query patterns
        - geographic_segments: List of locations
        - intent_profile: User intent description
        - priority: Priority level (1-5)
        - monthly_target: Target leads per month
        - daily_email_limit: Daily email limit

    Raises:
        LLMError: If LLM generation fails
    """
    system_message = """You are an expert at creating search bucket configurations for lead generation. 
Your job is to analyze a business type and generate optimal search patterns that potential clients would use to find such businesses.

Rules:
1. Search patterns should be realistic queries people actually type
2. Include variations with location modifiers
3. Categories should cover related business types
4. Keep it practical - max 10 search patterns
5. All output MUST be valid JSON"""

    locations_str = ", ".join(target_locations) if target_locations else "All India"

    prompt = f"""Generate a bucket configuration for '{business_type}' businesses targeting: {locations_str}

Return ONLY a JSON object with this exact structure (no markdown, no explanation):
{{
  "name": "{business_type.lower().replace(' ', '_')}",
  "categories": ["{business_type}", "related category 1", "related category 2"],
  "search_patterns": [
    "best {{service}} in {{city}}",
    "top rated {{service}} near me",
    "affordable {{service}} {{city}}"
  ],
  "geographic_segments": {json.dumps(target_locations)},
  "intent_profile": "Looking for professional {{service}} services in {{location}}",
  "priority": 3,
  "monthly_target": 100,
  "max_queries": {max_queries},
  "max_results": {max_results},
  "daily_email_limit": 50
}}

IMPORTANT: 
- Replace {{service}} with actual service terms for {business_type}
- Include 5-10 realistic search patterns
- Make categories specific to the business type
- Return ONLY valid JSON, no other text"""

    try:
        response = generate(
            prompt=prompt,
            system=system_message,
            format_json=True,
            timeout=LLM_TIMEOUT * 2,  # Give more time for complex generation
        )
        
        config = json.loads(response)
        
        # Validate required fields
        required_fields = ["name", "categories", "search_patterns", "geographic_segments"]
        missing_fields = [f for f in required_fields if f not in config]
        
        if missing_fields:
            raise LLMError(f"LLM response missing required fields: {', '.join(missing_fields)}")
        
        # Ensure name is safe
        config["name"] = config["name"].lower().replace(" ", "_").replace("-", "_")
        
        # Set defaults for optional fields
        config.setdefault("intent_profile", f"Looking for {business_type} services")
        config.setdefault("priority", 3)
        config.setdefault("monthly_target", 100)
        config.setdefault("max_queries", max_queries)
        config.setdefault("max_results", max_results)
        config.setdefault("daily_email_limit", 50)
        
        return config
        
    except json.JSONDecodeError as e:
        raise LLMError(f"Failed to parse LLM response as JSON: {e}")
    except LLMError:
        raise
    except Exception as e:
        raise LLMError(f"Bucket generation failed: {e}")
