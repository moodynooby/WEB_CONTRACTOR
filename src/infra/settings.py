"""Application Settings — single source of truth.

All config in Python. Edit directly in infra/config_defaults.py.
Secrets (API keys, credentials) load from environment variables.
"""

import os
import warnings
from pathlib import Path
from typing import Any, Final

from dotenv import load_dotenv
from infra import config_defaults

PROJECT_ROOT: Final[Path] = Path(__file__).parent.parent.parent
_ENV_FILE = PROJECT_ROOT / ".env"

load_dotenv(_ENV_FILE, override=True)


def _load_config() -> dict[str, Any]:
    """Load config from Python defaults."""
    return config_defaults.CONFIG


_cfg = _load_config()


def _section(name: str) -> dict[str, Any]:
    """Return a top-level section dict from the already-loaded _cfg (empty if missing)."""
    section = _cfg.get(name)
    return section if isinstance(section, dict) else {}


def get_section(name: str) -> dict[str, Any]:
    """Return a config section from the already-loaded _cfg dict.

    This is an O(1) dict lookup — no file I/O or re-parsing.
    """
    return _section(name)

_email = _section("email")
EMAIL_SIGNATURE: Final[str] = _email.get(
    "signature", "\n\nBest regards,\nWeb Contractor"
)
SMTP_SERVER: Final[str] = _email.get("smtp_server", "smtp.gmail.com")
SMTP_PORT: Final[int] = _email.get("smtp_port", 587)

_llm = _section("llm")
DEFAULT_PROVIDER: Final[str] = _llm.get("provider", "groq")
DEFAULT_MODEL: Final[str] = f"{DEFAULT_PROVIDER}/{_llm.get(DEFAULT_PROVIDER, {}).get('model', 'llama-3.3-70b-versatile')}"

_email_discovery = _section("email_discovery")
EMAIL_COMMON_PREFIXES: Final[list[str]] = _email_discovery.get(
    "common_prefixes", ["info", "contact", "hello", "support", "admin"]
)

_timeouts = _section("timeouts")
EMAIL_SCRAPE_TIMEOUT: Final[int] = _timeouts.get("email_scrape_seconds", 10)

_scraper = _section("scraper")
_DEFAULT_USER_AGENTS: Final[list[str]] = _scraper.get(
    "user_agents",
    [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    ],
)
DEFAULT_USER_AGENT: Final[str] = _DEFAULT_USER_AGENTS[0]

_qualification = _section("qualification")
EMAIL_MAX_RETRIES: Final[int] = _qualification.get("email_max_retries", 3)

_query_mgmt = _section("query_management")
STALE_QUERY_THRESHOLD: Final[int] = _query_mgmt.get("stale_threshold", 3)
STALE_QUERY_CLEANUP_DAYS: Final[int] = _query_mgmt.get("stale_cleanup_days", 30)

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
            result = sock.connect_ex((parsed.hostname or "localhost", parsed.port or 11434))
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
