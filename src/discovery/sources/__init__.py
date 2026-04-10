"""Source factory - imports all scrapers and provides unified interface."""

from typing import Any, Dict, List, Optional

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


def get_scraper(
    source_name: str, settings: Optional[Dict[str, Any]] = None
) -> Optional[BaseScraper]:
    """Get a scraper instance by source name.

    Args:
        source_name: Name of the scraper (e.g., 'google_maps', 'justdial')
        settings: Optional settings dict to pass to scraper

    Returns:
        Scraper instance or None if not found
    """
    source_class = ScraperRegistry.get(source_name)
    if source_class:
        return source_class(settings=settings)
    return None


def get_all_enabled_sources(
    settings: Dict[str, Any], region: str = "india"
) -> List[BaseScraper]:
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
        enabled_sources.append((instance, source_config.get("priority", 99)))

    enabled_sources.sort(key=lambda x: x[1])
    return [s[0] for s in enabled_sources]


__all__ = [
    "BaseScraper",
    "ScraperRegistry",
    "get_scraper",
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
