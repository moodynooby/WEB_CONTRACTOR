"""Application Settings — single source of truth.

All config in Python. Edit directly in infra/config_defaults.py.
Optional override via infra/config_override.json (auto-generated if needed).
Secrets (API keys, credentials) load from environment variables.
"""

import json
import os
import warnings
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from typing import Any, Final

from dotenv import load_dotenv

PROJECT_ROOT: Final[Path] = Path(__file__).parent.parent.parent
_ENV_FILE = PROJECT_ROOT / ".env"

# Load .env file early so all os.getenv() calls work
load_dotenv(_ENV_FILE, override=True)

CONFIG_DIR = PROJECT_ROOT / "src" / "infra"
DEFAULT_CONFIG_FILE = CONFIG_DIR / "config_defaults.py"
OVERRIDE_FILE = CONFIG_DIR / "config_override.json"


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _load_config() -> dict[str, Any]:
    """Load config from Python defaults + optional JSON override."""
    spec = spec_from_file_location("config_defaults", DEFAULT_CONFIG_FILE)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to load config module from {DEFAULT_CONFIG_FILE}")

    defaults = module_from_spec(spec)
    spec.loader.exec_module(defaults)

    config = defaults.CONFIG

    if OVERRIDE_FILE.exists():
        with open(OVERRIDE_FILE, "r") as f:
            override = json.load(f)
        config = _deep_merge(config, override)

    return config


def _section(name: str) -> dict[str, Any]:
    """Return a top-level section dict (empty if missing)."""
    cfg = _load_config()
    section = cfg.get(name)
    return section if isinstance(section, dict) else {}


def load_json_section(section: str) -> dict[str, Any]:
    """Return a top-level section from config."""
    return _section(section)


def get_config() -> dict[str, Any]:
    """Return full config dict."""
    return _load_config()


def generate_override_template() -> None:
    """Generate config_override.json template with current values."""
    current = _load_config()
    with open(OVERRIDE_FILE, "w") as f:
        json.dump(current, f, indent=2)
    print(f"Generated override template at {OVERRIDE_FILE}")


def update_config(section: str, updates: dict) -> None:
    """Update config section and save to override file."""
    current = get_config()
    current.setdefault(section, {}).update(updates)
    with open(OVERRIDE_FILE, "w") as f:
        json.dump(current, f, indent=2)


_cfg = _load_config()

LOG_LEVEL: Final[str] = _cfg.get("log_level", "INFO")

_server = _section("server")
STREAMLIT_PORT: Final[int] = _server.get("streamlit_port", 8501)

_email = _section("email")
EMAIL_SIGNATURE: Final[str] = _email.get(
    "signature", "\n\nBest regards,\nWeb Contractor"
)
SMTP_SERVER: Final[str] = _email.get("smtp_server", "smtp.gmail.com")
SMTP_PORT: Final[int] = _email.get("smtp_port", 587)

_llm = _section("llm")
LLM_MODE: Final[str] = _llm.get("mode", "cloud")
PERFORMANCE_MODE: Final[str] = _llm.get("performance_mode", "cloud_standard")
DEFAULT_PROVIDER: Final[str] = _llm.get("provider", "groq")
DEFAULT_MODEL: Final[str] = _llm.get("default_model", "llama-3.1-8b-instant")
FALLBACK_MODEL: Final[str] = _llm.get("fallback_model", "google/gemma-2-2b-it:free")
LLM_TIMEOUT: Final[int] = _llm.get("timeout_seconds", 30)

_local_llm = _llm.get("local", {})
LOCAL_PROVIDER: Final[str] = _local_llm.get("provider", "ollama")
LOCAL_BASE_URL: Final[str] = _local_llm.get("base_url", "http://localhost:11434/v1")
LOCAL_MODEL: Final[str] = _local_llm.get("model", "llama3.2:latest")
LOCAL_HARDWARE_PROFILE: Final[str] = _local_llm.get("hardware_profile", "auto")

_providers = _section("providers")
GROQ_BASE_URL: Final[str] = _providers.get("groq", {}).get(
    "base_url", "https://api.groq.com/openai/v1"
)
OPENROUTER_BASE_URL: Final[str] = _providers.get("openrouter", {}).get(
    "base_url", "https://openrouter.ai/api/v1"
)

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
