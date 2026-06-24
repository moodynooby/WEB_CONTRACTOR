"""Source factory - imports all scrapers and provides unified interface."""

from typing import Any

from .base import BaseScraper, ScraperRegistry
from . import (
    google_maps,
    google_search,
    justdial,
    sulekha,
    yellowpages,
    blogspot,
    wordpress,
    wix,
    website_filter,
)


def get_all_enabled_sources(
    settings: dict[str, Any], region: str = "india"
) -> list[BaseScraper]:
    """Get all enabled scraper sources sorted by priority, filtered by region.

    Args:
        settings: Full application settings dict
        region: Target region to filter sources (e.g., 'india', 'global')

    Returns:
        List of enabled scraper instances sorted by priority
    """
    sources_config = settings.get("discovery_sources", {}).get("sources", {})

    all_source_classes = ScraperRegistry.get_all_sources()

    enabled_sources = []
    for source_name, source_class in all_source_classes.items():
        source_config = sources_config.get(source_name, {})
        instance = source_class(settings=source_config)
        if not instance.is_enabled():
            continue
        enabled_sources.append((instance, source_config.get("priority", 99)))

    enabled_sources.sort(key=lambda x: x[1])
    return [s[0] for s in enabled_sources]


__all__ = [
    "BaseScraper",
    "ScraperRegistry",
    "get_all_enabled_sources",
    "google_maps",
    "google_search",
    "justdial",
    "sulekha",
    "yellowpages",
    "blogspot",
    "wordpress",
    "wix",
    "website_filter",
]
