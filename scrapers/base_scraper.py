from typing import List, Dict, Optional
from core.lead_buckets import LeadBucketManager
from core.rate_limiter import get_scraper
from core.db import LeadRepository
from core.selenium_utils import SeleniumDriverFactory
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException


class BaseScraper:
    """
    Base class for all scrapers, providing common utilities for:
    - Database operations (via LeadRepository)
    - Rate limiting (via core.rate_limiter)
    - Selenium interaction
    - Quality scoring
    """

    def __init__(self, source_name: str):
        self.source_name = source_name
        self.bucket_manager = LeadBucketManager()
        self.repo = LeadRepository()
        # Use centralized rate limiter
        self.ethical_scraper = get_scraper(source_name)
        self.session = self.ethical_scraper.session
        # Expose rate_limiter directly for non-HTTP scrapers (like Selenium)
        self.rate_limiter = self.ethical_scraper.rate_limiter
        self.driver = None

    def _init_driver(self, headless: bool = True):
        """Initialize and store Selenium driver"""
        if not self.driver:
            self.driver = SeleniumDriverFactory.create_driver(headless=headless)
        return self.driver

    def _close_driver(self):
        """Safely close Selenium driver"""
        if self.driver:
            SeleniumDriverFactory.safe_close(self.driver)
            self.driver = None

    def wait_for_element(self, selector: str, by=By.CSS_SELECTOR, timeout=10):
        """Wait for an element to be present"""
        if not self.driver:
            return None
        try:
            return WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((by, selector))
            )
        except TimeoutException:
            return None

    def safe_find_elements(self, selector: str, by=By.CSS_SELECTOR):
        """Safely find multiple elements"""
        if not self.driver:
            return []
        try:
            return self.driver.find_elements(by, selector)
        except:
            return []

    def safe_get_text(
        self, element, selector: str, by=By.CSS_SELECTOR, default: str = ""
    ):
        """Safely get text from a sub-element"""
        try:
            return element.find_element(by, selector).text.strip()
        except:
            return default

    def safe_get_attribute(
        self,
        element,
        selector: str,
        attribute: str,
        by=By.CSS_SELECTOR,
        default: str = "",
    ):
        """Safely get attribute from a sub-element"""
        try:
            return element.find_element(by, selector).get_attribute(attribute)
        except:
            return default

    def save_to_database(self, leads: List[Dict], source: Optional[str] = None) -> int:
        """
        Common method to save leads to database.
        Handles duplicates and logging.
        """
        if not leads:
            return 0

        src = source or self.source_name
        print(f"Saving {len(leads)} leads to database from {src}...")

        saved_count = self.repo.add_leads_bulk(leads)

        print(f"\n✓ Saved {saved_count} new leads to database from {src}")

        # Log this scraping session
        self.repo.log_scraping_session(
            source=src,
            query=f"Batch save {len(leads)} leads",
            leads_found=len(leads),
            leads_saved=saved_count,
        )

        return saved_count

    def calculate_quality_score(self, lead_data: Dict) -> float:
        """Wrapper around bucket_manager's quality score"""
        return self.bucket_manager.calculate_lead_quality_score(lead_data)

    def extract_city_from_text(
        self, text: str, target_city: Optional[str] = None
    ) -> str:
        """
        Extract city from text. If target_city is provided, checks for it.
        Otherwise uses a general extraction logic.
        """
        if not text:
            return target_city or "Unknown"

        if target_city and target_city.lower() in text.lower():
            return target_city

        # Fallback to simple comma parsing
        parts = text.split(",")
        if len(parts) >= 2:
            return parts[-2].strip()

        return target_city or "Unknown"

    def determine_category(self, text: str, default: str = "Other") -> str:
        """
        Dynamically determine category based on LeadBucketManager definitions.
        """
        if not text:
            return default

        text = text.lower()

        # Check all buckets and their categories
        for bucket in self.bucket_manager.buckets:
            for category in bucket.categories:
                if category.lower() in text:
                    return category

            # Also check bucket name keywords
            if bucket.name.lower() in text:
                return bucket.categories[0]

        return default
