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

LOG_LEVEL: Final[str] = _cfg.get("log_level", "INFO")

_email = _section("email")
EMAIL_SIGNATURE: Final[str] = _email.get(
    "signature", "\n\nBest regards,\nWeb Contractor"
)
SMTP_SERVER: Final[str] = _email.get("smtp_server", "smtp.gmail.com")
SMTP_PORT: Final[int] = _email.get("smtp_port", 587)

_llm = _section("llm")
LLM_MODE: Final[str] = "cloud"  
DEFAULT_PROVIDER: Final[str] = _llm.get("provider", "groq")
DEFAULT_MODEL: Final[str] = f"{DEFAULT_PROVIDER}/{_llm.get(DEFAULT_PROVIDER, {}).get('model', 'llama-3.3-70b-versatile')}"
FALLBACK_MODEL: Final[str] = DEFAULT_MODEL
LLM_TIMEOUT: Final[int] = _llm.get("timeout_seconds", 30)

_local_llm = _llm.get("ollama", {})
LOCAL_PROVIDER: Final[str] = "ollama"
LOCAL_BASE_URL: Final[str] = _local_llm.get("base_url", "http://localhost:11434")
LOCAL_MODEL: Final[str] = f"ollama/{_local_llm.get('model', 'llama3.2:latest')}"
LOCAL_HARDWARE_PROFILE: Final[str] = "auto"

GROQ_BASE_URL: Final[str] = "https://api.groq.com/openai/v1"
OPENROUTER_BASE_URL: Final[str] = "https://openrouter.ai/api/v1"

_timeouts = _section("timeouts")
CONNECTION_TEST_TIMEOUT: Final[int] = _timeouts.get("connection_test_seconds", 5)
HTTP_REQUEST_TIMEOUT: Final[int] = _timeouts.get("http_request_seconds", 15)
PAGE_FETCH_TIMEOUT: Final[int] = _timeouts.get("page_fetch_seconds", 15)
EMAIL_SCRAPE_TIMEOUT: Final[int] = _timeouts.get("email_scrape_seconds", 10)

_email_discovery = _section("email_discovery")
EMAIL_COMMON_PREFIXES: Final[list[str]] = _email_discovery.get(
    "common_prefixes", ["info", "contact", "hello", "support", "admin"]
)

_pipeline = _section("pipeline")
PIPELINE_MAX_QUERIES: Final[int] = _pipeline.get("defaults", {}).get("max_queries", 20)
PIPELINE_AUDIT_LIMIT: Final[int] = _pipeline.get("defaults", {}).get("audit_limit", 20)
PIPELINE_EMAIL_LIMIT: Final[int] = _pipeline.get("defaults", {}).get("email_limit", 20)

_scraper = _section("scraper")
SCRAPER_HEADLESS: Final[bool] = _scraper.get("headless", True)
VERIFY_SSL: Final[bool] = _scraper.get("verify_ssl", True)
PAGE_LOAD_TIMEOUT_MS: Final[int] = _scraper.get("page_load_timeout_ms", 5000)
SEARCH_WAIT_TIMEOUT_MS: Final[int] = _scraper.get("search_wait_timeout_ms", 10000)
RESULT_CLICK_DELAY_MS: Final[int] = _scraper.get("result_click_delay_ms", 2000)
_USER_AGENTS: Final[list[str]] = _scraper.get(
    "user_agents",
    [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    ],
)
USER_AGENTS: Final[list[str]] = _USER_AGENTS
DEFAULT_USER_AGENT: Final[str] = _USER_AGENTS[0]

_qualification = _section("qualification")
AUDIT_SCORE_THRESHOLD: Final[int] = _qualification.get("score_threshold", 90)
EMAIL_GENERATION_LIMIT: Final[int] = _qualification.get("email_generation_limit", 20)
EMAIL_MAX_RETRIES: Final[int] = _qualification.get("email_max_retries", 3)

_query_mgmt = _section("query_management")
STALE_QUERY_THRESHOLD: Final[int] = _query_mgmt.get("stale_threshold", 3)
STALE_QUERY_CLEANUP_DAYS: Final[int] = _query_mgmt.get("stale_cleanup_days", 30)

_parallel = _section("parallel")
PARALLEL_MAX_WORKERS: Final[int] = _parallel.get("max_workers", 3)
PARALLEL_TIMEOUT_PER_SOURCE_SECONDS: Final[int] = _parallel.get(
    "timeout_per_source_seconds", 30
)

GROQ_API_KEY: Final[str] = os.getenv("GROQ_API_KEY", "")
OPENROUTER_API_KEY: Final[str] = os.getenv("OPENROUTER_API_KEY", "")
GMAIL_EMAIL: Final[str] = os.getenv("GMAIL_EMAIL", "")
GMAIL_PASSWORD: Final[str] = os.getenv("GMAIL_PASSWORD", "")
TELEGRAM_BOT_TOKEN: Final[str] = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID: Final[str] = os.getenv("TELEGRAM_CHAT_ID", "")

MONGODB_URI: Final[str] = os.getenv("MONGODB_URI", "")
MONGODB_DATABASE: Final[str] = os.getenv("MONGODB_DATABASE", "web_contractor")

OLLAMA_API_BASE: Final[str] = os.getenv("OLLAMA_API_BASE", "http://localhost:11434")
OLLAMA_MODEL: Final[str] = os.getenv("OLLAMA_MODEL", "llama3.2:latest")

LM_STUDIO_API_BASE: Final[str] = os.getenv(
    "LM_STUDIO_API_BASE", "http://localhost:1234/v1"
)
LM_STUDIO_MODEL: Final[str] = os.getenv("LM_STUDIO_MODEL", "local-model")
LM_STUDIO_API_KEY: Final[str] = os.getenv("LM_STUDIO_API_KEY", "")


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
