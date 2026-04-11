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


def get_llm_model():
    """Get the configured LLM model (string or LiteLlm instance).

    Returns:
        For Gemini: a plain model name string (``"gemini/gemini-2.0-flash"``).
        For all others: a ``LiteLlm`` instance that wraps the provider.

    The provider is selected from ``config_defaults.py`` section
    ``llm.provider``.  Supported values: ``gemini``, ``groq``,
    ``openrouter``, ``ollama``, ``lm_studio``, ``anthropic``.
    """
    config = _get_llm_config()
    provider = config.get("provider", "groq")

    if provider in _model_cache:
        return _model_cache[provider]

    if provider == "gemini":
        gemini_cfg = config.get("gemini", {})
        model_name = f"gemini/{gemini_cfg.get('model', 'gemini-2.0-flash')}"
        logger.info(f"LLM model: Gemini — {model_name}")
        _model_cache[provider] = model_name
        return model_name

    from google.adk.models.lite_llm import LiteLlm

    provider_configs = {
        "groq": config.get("groq", {}),
        "openrouter": config.get("openrouter", {}),
        "ollama": config.get("ollama", {}),
        "lm_studio": config.get("lm_studio", {}),
        "anthropic": config.get("anthropic", {}),
    }

    p_config = provider_configs.get(provider, {})
    model_id = p_config.get("model", "")

    if not model_id:
        logger.warning(
            f"No model configured for provider '{provider}', falling back to groq/llama-3.3-70b-versatile"
        )
        model_name = "groq/llama-3.3-70b-versatile"
        _model_cache["groq"] = LiteLlm(model=model_name)
        return _model_cache["groq"]

    import os

    if provider == "ollama":
        base_url = p_config.get("base_url", "http://localhost:11434")
        os.environ.setdefault("OLLAMA_API_BASE", base_url)
        os.environ.setdefault("OPENAI_API_BASE", f"{base_url}/v1")
        os.environ.setdefault("OPENAI_API_KEY", "ollama")
        lite_model = f"ollama/{model_id}"
    elif provider == "lm_studio":
        base_url = p_config.get("base_url", "http://localhost:1234/v1")
        api_key = p_config.get("api_key", "") or "lm-studio"
        os.environ.setdefault("OPENAI_API_BASE", base_url)
        os.environ.setdefault("OPENAI_API_KEY", api_key)
        lite_model = f"openai/{model_id}"
    else:
        lite_model = f"{provider}/{model_id}"

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