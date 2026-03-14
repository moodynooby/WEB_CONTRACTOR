"""Base scraper class and common utilities for all scraping sources."""

import re
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlparse

from playwright.sync_api import Page

try:
    from email_scraper import scrape_emails
except ImportError:
    scrape_emails = None


class ScraperError(Exception):
    """Base exception for scraper errors."""

    pass


class SourceUnavailableError(ScraperError):
    """Raised when source is unavailable or blocked."""

    pass


class EmailExtractor:
    """Utility class for extracting emails from text/HTML.

    Uses email-scraper library for obfuscated email detection,
    with regex fallback if library unavailable.
    """

    EMAIL_PATTERN = re.compile(
        r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", re.IGNORECASE
    )

    @classmethod
    def extract_from_text(cls, text: str) -> List[str]:
        """Extract emails from plain text using regex."""
        if not text:
            return []
        return list(set(cls.EMAIL_PATTERN.findall(text)))

    @classmethod
    def extract_from_html(cls, html: str) -> List[str]:
        """Extract emails from HTML content using email-scraper."""
        if not html:
            return []

        if scrape_emails is not None:
            scraped = scrape_emails(html)
            return list(scraped) if scraped else []

        return cls.extract_from_text(html)

    @classmethod
    def extract_first(cls, text: str) -> Optional[str]:
        """Extract first email from text."""
        matches = cls.extract_from_text(text)
        return matches[0] if matches else None


class PhoneExtractor:
    """Utility class for extracting phone numbers from text/HTML."""

    PHONE_PATTERNS = [
        re.compile(r"\+?91[\s\-]?[6-9]\d{9}"),
        re.compile(r"\+?\d{1,3}[\s\-]?\d{6,12}"),
        re.compile(r"\(?\d{2,5}\)?[\s\-]?\d{4,8}"),
    ]

    @classmethod
    def extract_from_text(cls, text: str) -> List[str]:
        """Extract phone numbers from plain text."""
        if not text:
            return []
        numbers = []
        for pattern in cls.PHONE_PATTERNS:
            matches = pattern.findall(text)
            numbers.extend(matches)
        return list(set(numbers))

    @classmethod
    def extract_first(cls, text: str) -> Optional[str]:
        """Extract first phone number from text."""
        matches = cls.extract_from_text(text)
        return matches[0] if matches else None


class BaseScraper(ABC):
    """Abstract base class for all scraping sources.

    Each source (Google Maps, JustDial, etc.) should inherit from this
    and implement the source-specific extraction logic.
    """

    SOURCE_NAME: str = ""
    BASE_URL: str = ""

    DEFAULT_SELECTORS: Dict[str, str] = {}

    def __init__(
        self,
        logger: Callable | None = None,
        settings: Optional[Dict[str, Any]] = None,
    ):
        self.logger = logger
        self.settings = settings or {}

    def log(self, message: str, style: str = "") -> None:
        """Log message using provided logger or print."""
        if self.logger:
            self.logger(message, style)
        else:
            print(message)

    @abstractmethod
    def search(
        self, query: str, page: Page, max_results: int = 5
    ) -> List[Dict[str, Any]]:
        """Search for businesses and extract lead data.

        Args:
            query: Search query string
            page: Playwright page object
            max_results: Maximum number of results to extract

        Returns:
            List of lead dictionaries with normalized schema
        """
        pass

    def normalize_lead(
        self,
        data: Dict[str, Any],
        bucket: str = "",
        query: str = "",
    ) -> Dict[str, Any]:
        """Normalize lead data to common schema.

        Args:
            data: Raw lead data from source
            bucket: Bucket name this lead belongs to
            query: Original search query

        Returns:
            Normalized lead dictionary
        """
        return {
            "business_name": data.get("business_name")
            or data.get("name")
            or "Unknown Business",
            "website": self._normalize_url(
                data.get("website") or data.get("website_url")
            ),
            "phone": data.get("phone") or data.get("mobile") or data.get("contact"),
            "email": data.get("email") or data.get("contact_email"),
            "source": self.SOURCE_NAME,
            "bucket": bucket,
            "category": self._extract_category_from_query(query),
            "location": data.get("location") or data.get("address") or "",
            "listing_url": data.get("listing_url") or data.get("url") or "",
        }

    def _normalize_url(self, url: Optional[str]) -> Optional[str]:
        """Normalize URL to consistent format."""
        if not url:
            return None
        url = url.strip()
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"
        try:
            parsed = urlparse(url)
            if parsed.netloc:
                return url
        except Exception as e:
            self.log(f"Error normalizing URL: {e}", "error")
        return None

    def _extract_category_from_query(self, query: str) -> str:
        """Extract category from search query."""
        if not query:
            return "Unknown"
        return query.split()[0] if " " in query else query

    def _extract_emails_from_page(self, page: Page) -> List[str]:
        """Extract emails visible on current page."""
        try:
            content = page.content()
            return EmailExtractor.extract_from_html(content)
        except Exception as e:
            self.log(f"Error extracting emails from page: {e}", "error")
            return []

    def _extract_phones_from_page(self, page: Page) -> List[str]:
        """Extract phone numbers visible on current page."""
        try:
            content = page.content()
            return PhoneExtractor.extract_from_text(content)
        except Exception as e:
            self.log(f"Error extracting phones from page: {e}", "error")
            return []

    def get_source_config(self) -> Dict[str, Any]:
        """Get source-specific configuration."""
        return self.settings.get(self.SOURCE_NAME, {})

    def is_enabled(self) -> bool:
        """Check if this source is enabled in config."""
        config = self.get_source_config()
        return config.get("enabled", True)

    def get_priority(self) -> int:
        """Get source priority (lower = higher priority)."""
        config = self.get_source_config()
        return config.get("priority", 99)

    def get_max_results(self) -> int:
        """Get max results per query for this source."""
        config = self.get_source_config()
        return config.get("max_results", 5)


class ScraperRegistry:
    """Registry for managing all available scraper sources."""

    _sources: Dict[str, type[BaseScraper]] = {}

    @classmethod
    def register(cls, source_class: type[BaseScraper]) -> None:
        """Register a scraper source class."""
        if not issubclass(source_class, BaseScraper):
            raise TypeError(f"{source_class} must inherit from BaseScraper")
        instance = source_class()
        cls._sources[instance.SOURCE_NAME] = source_class

    @classmethod
    def get(cls, source_name: str) -> Optional[type[BaseScraper]]:
        """Get scraper class by source name."""
        return cls._sources.get(source_name)

    @classmethod
    def get_all_sources(cls) -> Dict[str, type[BaseScraper]]:
        """Get all registered scraper sources."""
        return cls._sources.copy()

    @classmethod
    def get_enabled_sources(cls, config: Dict[str, Any]) -> List[type[BaseScraper]]:
        """Get all enabled sources sorted by priority."""
        enabled = []
        for source_class in cls._sources.values():
            instance = source_class()
            if instance.is_enabled():
                instance.settings = config
                enabled.append((source_class, instance.get_priority()))

        enabled.sort(key=lambda x: x[1])
        return [s[0] for s in enabled]
