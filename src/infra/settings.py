"""Application Settings — single source of truth.

Config loaded from config/default.yaml with Pydantic validation.
Secrets (API keys, credentials) load from environment variables.
"""

import os
import warnings
from pathlib import Path
from typing import Any, Final

import yaml
from dotenv import load_dotenv
from pydantic import ValidationError

from infra.config_schema import AppConfig

PROJECT_ROOT: Final[Path] = Path(__file__).parent.parent.parent
_ENV_FILE = PROJECT_ROOT / ".env"
_CONFIG_FILE = PROJECT_ROOT / "config" / "default.yaml"

load_dotenv(_ENV_FILE, override=True)


def _load_config() -> AppConfig:
    """Load config from YAML file with validation."""
    if _CONFIG_FILE.exists():
        with open(_CONFIG_FILE, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        try:
            return AppConfig(**raw)
        except ValidationError as e:
            warnings.warn(f"Invalid config in {_CONFIG_FILE}: {e}", RuntimeWarning)
    return AppConfig()


_config: AppConfig = _load_config()


def get_config() -> AppConfig:
    """Return the validated config object."""
    return _config


def get_section(name: str) -> dict[str, Any]:
    """Return a config section as a dict for backward compatibility."""
    section = getattr(_config, name, None)
    if section is None:
        return {}
    return section.model_dump() if hasattr(section, "model_dump") else {}


EMAIL_SIGNATURE: Final[str] = _config.email.signature
SMTP_SERVER: Final[str] = _config.email.smtp_server
SMTP_PORT: Final[int] = _config.email.smtp_port

DEFAULT_PROVIDER: Final[str] = _config.llm.provider
DEFAULT_MODEL: Final[str] = (
    f"{DEFAULT_PROVIDER}/{getattr(_config.llm, DEFAULT_PROVIDER, _config.llm.ollama).model}"
)

EMAIL_COMMON_PREFIXES: Final[list[str]] = ["info", "contact", "hello", "support", "admin"]

EMAIL_SCRAPE_TIMEOUT: Final[int] = _config.timeouts.email_scrape_seconds

DEFAULT_USER_AGENT: Final[str] = _config.scraper.user_agents[0] if _config.scraper.user_agents else ""

EMAIL_MAX_RETRIES: Final[int] = 3

STALE_QUERY_THRESHOLD: Final[int] = _config.query_management.stale_query_threshold
STALE_QUERY_CLEANUP_DAYS: Final[int] = _config.query_management.stale_cleanup_days

GROQ_API_KEY: Final[str] = os.getenv("GROQ_API_KEY", "")
OPENROUTER_API_KEY: Final[str] = os.getenv("OPENROUTER_API_KEY", "")
GMAIL_EMAIL: Final[str] = os.getenv("GMAIL_EMAIL", "")
GMAIL_PASSWORD: Final[str] = os.getenv("GMAIL_PASSWORD", "")
TELEGRAM_BOT_TOKEN: Final[str] = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID: Final[str] = os.getenv("TELEGRAM_CHAT_ID", "")

MONGODB_URI: Final[str] = os.getenv("MONGODB_URI", "")
MONGODB_DATABASE: Final[str] = os.getenv("MONGODB_DATABASE", "web_contractor")

OLLAMA_API_BASE: Final[str] = os.getenv("OLLAMA_API_BASE", "http://localhost:11434")

LM_STUDIO_API_BASE: Final[str] = os.getenv(
    "LM_STUDIO_API_BASE", "http://localhost:1234/v1"
)


def _validate_mongodb_uri(uri: str) -> bool:
    if not uri:
        return False
    valid_prefixes = ("mongodb://", "mongodb+srv://")
    if not any(uri.startswith(prefix) for prefix in valid_prefixes):
        return False
    if "mongodb+srv://" in uri or "mongodb://" in uri:
        if "localhost" in uri or "127.0.0.1" in uri:
            return True
        if "@" not in uri and "localhost" not in uri:
            return False
    return True


def _validate_secrets() -> None:
    if not _ENV_FILE.exists():
        warnings.warn(
            f"No .env file at {_ENV_FILE}. Copy .env.example to .env and fill in keys.",
            RuntimeWarning,
        )
    missing = [
        n
        for n, v in (
            ("GROQ_API_KEY", GROQ_API_KEY),
            ("OPENROUTER_API_KEY", OPENROUTER_API_KEY),
            ("GMAIL_EMAIL", GMAIL_EMAIL),
            ("GMAIL_PASSWORD", GMAIL_PASSWORD),
        )
        if not v
    ]
    if missing:
        warnings.warn(
            f"Missing secret(s): {', '.join(missing)}. Some features won't work.",
            RuntimeWarning,
        )

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        warnings.warn(
            "Telegram notifications not configured. Pipeline will run without notifications.",
            RuntimeWarning,
        )

    import socket

    for provider_name, url in [
        ("Ollama", OLLAMA_API_BASE),
        ("LM Studio", LM_STUDIO_API_BASE),
    ]:
        try:
            from urllib.parse import urlparse

            parsed = urlparse(url)
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(
                (parsed.hostname or "localhost", parsed.port or 11434)
            )
            sock.close()
            if result != 0:
                warnings.warn(
                    f"{provider_name} not reachable at {url}. "
                    f"Start {provider_name} before using local LLM mode.",
                    RuntimeWarning,
                )
        except Exception:
            pass

    if MONGODB_URI and not _validate_mongodb_uri(MONGODB_URI):
        warnings.warn(
            f"MONGODB_URI appears to be invalid. Got: {MONGODB_URI[:30]}...",
            RuntimeWarning,
        )
    elif not MONGODB_URI:
        warnings.warn(
            "MONGODB_URI not set. Database features will be disabled.", RuntimeWarning
        )


_validate_secrets()
