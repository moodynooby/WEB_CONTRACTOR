"""Rate limit protection for cloud LLM providers.

Tracks API usage and enforces rate limits to prevent hitting provider quotas.
Supports both Groq and OpenRouter rate limit policies.
"""

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from infra.logging import get_logger

logger = get_logger(__name__)


@dataclass
class RateLimitConfig:
    """Rate limit configuration for a provider."""

    rpm_limit: int = 30
    tpm_limit: int = 60000
    rpd_limit: int = 10000
    enabled: bool = True
    safety_buffer_pct: float = 0.10
    cooldown_seconds: float = 60.0


@dataclass
class UsageWindow:
    """Sliding window tracker for API usage."""

    max_size: int = 1000
    requests: deque = field(default_factory=lambda: deque(maxlen=1000))

    def add(self, tokens_used: int = 0):
        """Record a request with token usage."""
        self.requests.append((time.time(), tokens_used))

    def count_recent(self, window_seconds: float = 60.0) -> tuple[int, int]:
        """Count requests and tokens in recent window."""
        cutoff = time.time() - window_seconds
        count = 0
        tokens = 0
        for timestamp, token_count in self.requests:
            if timestamp >= cutoff:
                count += 1
                tokens += token_count
        return count, tokens

    def count_today(self) -> tuple[int, int]:
        """Count requests and tokens since midnight."""
        import datetime

        midnight = datetime.datetime.now().replace(
            hour=0, minute=0, second=0, microsecond=0
        ).timestamp()
        count = 0
        tokens = 0
        for timestamp, token_count in self.requests:
            if timestamp >= midnight:
                count += 1
                tokens += token_count
        return count, tokens


@dataclass
class ProviderUsage:
    """Track usage for a single provider."""

    config: RateLimitConfig
    window: UsageWindow = field(default_factory=UsageWindow)
    lock: threading.Lock = field(default_factory=threading.Lock)
    cooldown_until: float = 0.0
    rate_limit_hits: int = 0
    last_rate_limit_error: float = 0.0


class RateLimitProtector:
    """Global rate limit protector for all LLM providers."""

    def __init__(self):
        self._providers: dict[str, ProviderUsage] = {}
        self._lock = threading.Lock()

    def configure_provider(
        self,
        provider_name: str,
        rpm_limit: int = 30,
        tpm_limit: int = 60000,
        rpd_limit: int = 10000,
        enabled: bool = True,
        safety_buffer_pct: float = 0.10,
        cooldown_seconds: float = 60.0,
    ):
        """Configure rate limits for a provider."""
        with self._lock:
            self._providers[provider_name] = ProviderUsage(
                config=RateLimitConfig(
                    rpm_limit=rpm_limit,
                    tpm_limit=tpm_limit,
                    rpd_limit=rpd_limit,
                    enabled=enabled,
                    safety_buffer_pct=safety_buffer_pct,
                    cooldown_seconds=cooldown_seconds,
                )
            )
            logger.info(
                f"Configured rate limit for {provider_name}: "
                f"RPM={rpm_limit}, TPM={tpm_limit}, RPD={rpd_limit}"
            )

    def _get_usage(self, provider_name: str) -> ProviderUsage | None:
        """Get provider usage tracker."""
        return self._providers.get(provider_name)

    def check_rate_limit(
        self, provider_name: str, estimated_tokens: int = 0
    ) -> tuple[bool, str]:
        """Check if we can make a request without hitting rate limits.

        Args:
            provider_name: Provider name (e.g., "groq", "openrouter")
            estimated_tokens: Estimated tokens for this request

        Returns:
            Tuple of (allowed: bool, reason: str)
        """
        usage = self._get_usage(provider_name)
        if not usage or not usage.config.enabled:
            return True, "Rate limiting disabled"

        with usage.lock:
            if time.time() < usage.cooldown_until:
                remaining = usage.cooldown_until - time.time()
                return (
                    False,
                    f"Cooldown active for {provider_name}, retry in {remaining:.0f}s",
                )

            effective_rpm = int(usage.config.rpm_limit * (1 - usage.config.safety_buffer_pct))
            rpm_count, _ = usage.window.count_recent(60.0)
            if rpm_count >= effective_rpm:
                logger.warning(
                    f"Rate limit approaching for {provider_name}: "
                    f"{rpm_count}/{effective_rpm} RPM (last minute)"
                )
                usage.cooldown_until = time.time() + usage.config.cooldown_seconds
                return False, f"RPM limit approaching: {rpm_count}/{effective_rpm}"

            effective_tpm = int(usage.config.tpm_limit * (1 - usage.config.safety_buffer_pct))
            _, tpm_count = usage.window.count_recent(60.0)
            if tpm_count + estimated_tokens >= effective_tpm:
                logger.warning(
                    f"Rate limit approaching for {provider_name}: "
                    f"{tpm_count}/{effective_tpm} TPM (last minute)"
                )
                usage.cooldown_until = time.time() + usage.config.cooldown_seconds
                return False, f"TPM limit approaching: {tpm_count}/{effective_tpm}"

            effective_rpd = int(usage.config.rpd_limit * (1 - usage.config.safety_buffer_pct))
            rpd_count, _ = usage.window.count_today()
            if rpd_count >= effective_rpd:
                logger.warning(
                    f"Rate limit approaching for {provider_name}: "
                    f"{rpd_count}/{effective_rpd} RPD (today)"
                )
                usage.cooldown_until = time.time() + usage.config.cooldown_seconds
                return False, f"RPD limit approaching: {rpd_count}/{effective_rpd}"

            return True, "Within limits"

    def record_request(self, provider_name: str, tokens_used: int = 0):
        """Record a successful API request."""
        usage = self._get_usage(provider_name)
        if not usage:
            return

        with usage.lock:
            usage.window.add(tokens_used)

    def record_rate_limit_error(self, provider_name: str):
        """Record a rate limit error (HTTP 429)."""
        usage = self._get_usage(provider_name)
        if not usage:
            return

        with usage.lock:
            usage.rate_limit_hits += 1
            usage.last_rate_limit_error = time.time()

            backoff_multiplier = min(usage.rate_limit_hits, 5)
            cooldown = usage.config.cooldown_seconds * (2 ** (backoff_multiplier - 1))

            usage.cooldown_until = time.time() + cooldown
            logger.warning(
                f"Rate limit error #{usage.rate_limit_hits} for {provider_name}, "
                f"cooldown {cooldown:.0f}s"
            )

    def get_usage_stats(self, provider_name: str) -> dict[str, Any]:
        """Get current usage statistics for a provider."""
        usage = self._get_usage(provider_name)
        if not usage:
            return {"error": f"Provider {provider_name} not configured"}

        with usage.lock:
            rpm_count, tpm_count = usage.window.count_recent(60.0)
            rpd_count, _ = usage.window.count_today()

            effective_rpm = int(usage.config.rpm_limit * (1 - usage.config.safety_buffer_pct))
            effective_tpm = int(usage.config.tpm_limit * (1 - usage.config.safety_buffer_pct))
            effective_rpd = int(usage.config.rpd_limit * (1 - usage.config.safety_buffer_pct))

            in_cooldown = time.time() < usage.cooldown_until
            cooldown_remaining = max(0, usage.cooldown_until - time.time()) if in_cooldown else 0

            return {
                "provider": provider_name,
                "rate_limiting_enabled": usage.config.enabled,
                "requests_last_minute": rpm_count,
                "tokens_last_minute": tpm_count,
                "requests_today": rpd_count,
                "rpm_limit": usage.config.rpm_limit,
                "rpm_effective_limit": effective_rpm,
                "tpm_limit": usage.config.tpm_limit,
                "tpm_effective_limit": effective_tpm,
                "rpd_limit": usage.config.rpd_limit,
                "rpd_effective_limit": effective_rpd,
                "rpm_usage_pct": round((rpm_count / usage.config.rpm_limit) * 100, 1) if usage.config.rpm_limit > 0 else 0,
                "tpm_usage_pct": round((tpm_count / usage.config.tpm_limit) * 100, 1) if usage.config.tpm_limit > 0 else 0,
                "rpd_usage_pct": round((rpd_count / usage.config.rpd_limit) * 100, 1) if usage.config.rpd_limit > 0 else 0,
                "in_cooldown": in_cooldown,
                "cooldown_remaining_seconds": round(cooldown_remaining, 1),
                "rate_limit_errors": usage.rate_limit_hits,
                "last_rate_limit_error": time.strftime(
                    "%Y-%m-%d %H:%M:%S", time.localtime(usage.last_rate_limit_error)
                ) if usage.last_rate_limit_error > 0 else "Never",
            }

    def reset_stats(self, provider_name: str | None = None):
        """Reset usage statistics."""
        with self._lock:
            if provider_name:
                usage = self._providers.get(provider_name)
                if usage:
                    with usage.lock:
                        usage.window = UsageWindow()
                        usage.rate_limit_hits = 0
                        usage.cooldown_until = 0.0
                        logger.info(f"Reset rate limit stats for {provider_name}")
            else:
                for name in self._providers:
                    usage = self._providers[name]
                    with usage.lock:
                        usage.window = UsageWindow()
                        usage.rate_limit_hits = 0
                        usage.cooldown_until = 0.0
                logger.info("Reset rate limit stats for all providers")


_rate_protector = RateLimitProtector()


def get_rate_protector() -> RateLimitProtector:
    """Get the global rate limit protector instance."""
    return _rate_protector
