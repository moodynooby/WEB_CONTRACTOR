"""LLM Multi-Provider Model Factory.

Uses LiteLLM to route to 100+ LLM providers (Groq, OpenRouter, OpenAI,
Anthropic, Ollama, LM Studio, etc.) via a single config setting.

LiteLLm format:
- ``groq/llama-3.3-70b-versatile``
- ``openrouter/google/gemma-2-9b-it:free``
- ``ollama_chat/llama3.2:latest``
- ``openai/local-model`` (LM Studio)
- ``anthropic/claude-sonnet-4-6``
- ``gemini/gemini-2.0-flash``

Usage:
    from infra.llm_models import get_llm_model

    model = get_llm_model()
    agent = LlmAgent(model=model, name="...", instruction="...")
"""

from typing import Any

from infra.logging import get_logger
from infra.settings import get_section

logger = get_logger(__name__)

_model_cache: dict[str, Any] = {}


def _get_llm_config() -> dict[str, Any]:
    """Load the LLM configuration section."""
    return get_section("llm")


def get_llm_model_string() -> str:
    """Get the configured LLM model as a LiteLLM-formatted string.

    Returns model in LiteLLM format: "provider/model_name"
    Examples: "groq/llama-3.3-70b-versatile", "ollama/llama3.2:latest"
    """
    config = _get_llm_config()
    provider = config.get("provider", "groq")

    if provider == "gemini":
        gemini_cfg = config.get("gemini", {})
        model_id = gemini_cfg.get("model", "gemini-2.0-flash")
        return f"gemini/{model_id}"

    if provider == "ollama":
        ollama_cfg = config.get("ollama", {})
        model_id = ollama_cfg.get("model", "llama3.2:latest")
        base_url = ollama_cfg.get("base_url", "http://localhost:11434")
        import os
        os.environ.setdefault("OLLAMA_API_BASE", base_url)
        os.environ.setdefault("OPENAI_API_BASE", f"{base_url}/v1")
        os.environ.setdefault("OPENAI_API_KEY", "ollama")
        return f"ollama/{model_id}"

    if provider == "lm_studio":
        lm_cfg = config.get("lm_studio", {})
        model_id = lm_cfg.get("model", "local-model")
        base_url = lm_cfg.get("base_url", "http://localhost:1234/v1")
        api_key = lm_cfg.get("api_key", "") or "lm-studio"
        import os
        os.environ.setdefault("OPENAI_API_BASE", base_url)
        os.environ.setdefault("OPENAI_API_KEY", api_key)
        return f"openai/{model_id}"

    provider_cfg = config.get(provider, {})
    model_id = provider_cfg.get("model", "")

    if not model_id:
        logger.warning(
            f"No model configured for '{provider}', falling back to groq/llama-3.3-70b-versatile"
        )
        return "groq/llama-3.3-70b-versatile"

    return f"{provider}/{model_id}"


def get_llm_model():
    """Get the configured LLM model (string or LiteLlm instance).

    Returns:
        For Gemini: a plain model name string (``"gemini/gemini-2.0-flash"``).
        For all others: a ``LiteLlm`` instance that wraps the provider.
    """
    config = _get_llm_config()
    provider = config.get("provider", "groq")

    if provider in _model_cache:
        return _model_cache[provider]

    if provider == "gemini":
        model_name = get_llm_model_string()
        logger.info(f"LLM model: Gemini — {model_name}")
        _model_cache[provider] = model_name
        return model_name

    from google.adk.models.lite_llm import LiteLlm

    lite_model = get_llm_model_string()
    logger.info(f"LLM model: LiteLLm — {lite_model}")
    model = LiteLlm(model=lite_model)
    _model_cache[provider] = model
    return model


def get_available_providers() -> list[dict[str, str]]:
    """List all configured providers with their model IDs.

    Returns:
        List of dicts with ``key``, ``name``, and ``model`` fields.
    """
    config = _get_llm_config()
    current = config.get("provider", "groq")

    providers = []
    for key in ("gemini", "groq", "openrouter", "ollama", "lm_studio", "anthropic"):
        p_config = config.get(key, {})
        model = p_config.get("model", "")
        name = key.title()
        if key == "ollama":
            name = "Ollama (local)"
        elif key == "lm_studio":
            name = "LM Studio (local)"
        elif key == "groq":
            name = "Groq"
        elif key == "openrouter":
            name = "OpenRouter"
        elif key == "anthropic":
            name = "Anthropic"
        providers.append({
            "key": key,
            "name": name,
            "model": model or "(not configured)",
            "active": key == current,
        })
    return providers


def switch_provider(provider: str) -> str:
    """Switch the active LLM provider at runtime.

    Args:
        provider: Provider key (``gemini``, ``groq``, ``openrouter``,
            ``ollama``, ``anthropic``).

    Returns:
        The new provider name.
    """
    valid = ("gemini", "groq", "openrouter", "ollama", "lm_studio", "anthropic")
    if provider not in valid:
        raise ValueError(f"Invalid provider '{provider}'. Must be one of: {valid}")

    config = _get_llm_config()
    config["provider"] = provider

    _model_cache.clear()

    logger.info(f"LLM provider switched to {provider}")
    return provider