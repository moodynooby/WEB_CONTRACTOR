"""Application Settings — single source of truth.

Non-secret config loads from config/app_config.json.
Secrets (API keys, credentials) load from environment variables.
"""

import os
import warnings
from pathlib import Path
from typing import Any, Final

PROJECT_ROOT: Final[Path] = Path(__file__).parent.parent


def _load_config() -> dict[str, Any]:
    """Load and cache config from app_config.json."""
    import json

    cache_key = "app"
    _cache: dict[str, Any] = getattr(_load_config, "_cache", {})
    if cache_key in _cache:
        return _cache[cache_key]
    config_file = PROJECT_ROOT / "config" / "app_config.json"
    try:
        with open(config_file, "r") as f:
            data = json.load(f)
            _cache[cache_key] = data
            return data
    except FileNotFoundError:
        raise RuntimeError(f"Config file not found at {config_file}") from None
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON in {config_file}: {exc}") from exc


def _section(name: str) -> dict[str, Any]:
    """Return a top-level section dict (empty if missing)."""
    cfg = _load_config()
    section = cfg.get(name)
    return section if isinstance(section, dict) else {}


def _val(cfg: dict, key: str, default: Any) -> Any:
    return cfg.get(key, default)


def _int(cfg: dict, key: str, default: int) -> int:
    v = cfg.get(key, default)
    try:
        return int(v)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"'{key}' must be int, got {v!r}") from exc


def _bool(cfg: dict, key: str, default: bool) -> bool:
    v = cfg.get(key, default)
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.lower() in ("true", "1", "yes")
    return default


def load_json_section(section: str) -> dict[str, Any]:
    """Return a top-level section from app_config.json."""
    return _section(section)


_cfg = _load_config()

LOG_LEVEL: Final[str] = _val(_cfg, "log_level", "INFO")

_email = _section("email")
EMAIL_SIGNATURE: Final[str] = _email.get(
    "signature", "\n\nBest regards,\nWeb Contractor"
)
SMTP_SERVER: Final[str] = _email.get("smtp_server", "smtp.gmail.com")
SMTP_PORT: Final[int] = _int(_email, "smtp_port", 587)

_llm = _section("llm")
LLM_MODE: Final[str] = _llm.get("mode", "cloud")  
PERFORMANCE_MODE: Final[str] = _llm.get(
    "performance_mode", "fast"
)  
DEFAULT_PROVIDER: Final[str] = _llm.get("provider", "groq")
DEFAULT_MODEL: Final[str] = _llm.get("default_model", "llama-3.1-8b-instant")
FALLBACK_MODEL: Final[str] = _llm.get("fallback_model", "google/gemma-2-2b-it:free")
LLM_TIMEOUT: Final[int] = _int(_llm, "timeout_seconds", 30)

_local_llm = _llm.get("local", {})
LOCAL_PROVIDER: Final[str] = _local_llm.get(
    "provider", "ollama"
)  
LOCAL_BASE_URL: Final[str] = _local_llm.get("base_url", "http://localhost:11434/v1")
LOCAL_MODEL: Final[str] = _local_llm.get("model", "llama3.2:latest")
LOCAL_HARDWARE_PROFILE: Final[str] = _local_llm.get(
    "hardware_profile", "auto"
)  

GROQ_BASE_URL: Final[str] = "https://api.groq.com/openai/v1"
OPENROUTER_BASE_URL: Final[str] = "https://openrouter.ai/api/v1"

_scraper = _section("scraper")
SCRAPER_HEADLESS: Final[bool] = _bool(_scraper, "headless", True)
VERIFY_SSL: Final[bool] = _bool(_scraper, "verify_ssl", True)
PAGE_LOAD_TIMEOUT_MS: Final[int] = _int(_scraper, "page_load_timeout_ms", 5000)
SEARCH_WAIT_TIMEOUT_MS: Final[int] = _int(_scraper, "search_wait_timeout_ms", 10000)
RESULT_CLICK_DELAY_MS: Final[int] = _int(_scraper, "result_click_delay_ms", 2000)
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


def _validate_mongodb_uri(uri: str) -> bool:
    """Basic validation of MongoDB URI format."""
    if not uri:
        return False
    valid_prefixes = (
        "mongodb://",
        "mongodb+srv://",
    )
    if not any(uri.startswith(prefix) for prefix in valid_prefixes):
        return False
    if "mongodb+srv://" in uri or "mongodb://" in uri:
        if "localhost" in uri or "127.0.0.1" in uri:
            return True
        if "@" not in uri and "localhost" not in uri:
            return False
    return True


_ENV_FILE = PROJECT_ROOT / ".env"


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

    if MONGODB_URI and not _validate_mongodb_uri(MONGODB_URI):
        warnings.warn(
            f"MONGODB_URI appears to be invalid. Ensure it starts with 'mongodb://' or 'mongodb+srv://'. Got: {MONGODB_URI[:30]}...",
            RuntimeWarning,
        )
    elif not MONGODB_URI:
        warnings.warn(
            "MONGODB_URI not set. Database features will be disabled.",
            RuntimeWarning,
        )


_validate_secrets()
