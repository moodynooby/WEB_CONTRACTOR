"""Sulekha scraper implementation."""

import time
from typing import Any, Dict, List

from playwright.sync_api import Page

from discovery.sources.base import BaseScraper, ScraperRegistry


class SulekhaScraper(BaseScraper):
    """Scraper for Sulekha (Indian community network)."""

    SOURCE_NAME = "sulekha"
    BASE_URL = "https://www.sulekha.com"

    SELECTORS = {
        "search_box": "input#searchQuery",
        "search_button": "button.search-btn",
        "results_container": "div.listing-list",
        "result_card": "div.business-listing-item",
        "business_name": "h3.business-name a",
        "phone": "span.phone-number",
        "address": "p.address",
        "website": "a.website-link",
    }

    def search(
        self, query: str, page: Page, max_results: int = 10
    ) -> List[Dict[str, Any]]:
        """Search Sulekha for businesses matching query.

        Args:
            query: Search query (e.g., "web developers Mumbai")
            page: Playwright page object
            max_results: Maximum number of results to extract

        Returns:
            List of lead dictionaries
        """
        leads: List[Dict[str, Any]] = []

        try:
            search_url = f"{self.BASE_URL}/city/mumbai/{query.replace(' ', '-')}"
            page.goto(search_url, wait_until="domcontentloaded")
            page.wait_for_timeout(self.settings.get("page_load_timeout_ms", 5000))

            try:
                page.wait_for_selector(
                    self.SELECTORS["result_card"],
                    timeout=self.settings.get("search_wait_timeout_ms", 10000),
                )
            except Exception:
                self.log(f"No results found for query: {query}", "error")
                return leads

            page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
            time.sleep(1)

            result_cards = page.query_selector_all(self.SELECTORS["result_card"])
            result_cards = result_cards[:max_results]

            for i, card in enumerate(result_cards):
                try:
                    lead = self._extract_lead_from_card(card, query)
                    if lead:
                        leads.append(lead)
                except Exception as e:
                    self.log(f"Error extracting lead from card: {e}", "error")
                    continue

        except Exception as e:
            self.log(f"Error searching Sulekha: {e}", "error")

        return leads

    def _extract_lead_from_card(self, card: Any, query: str) -> Dict[str, Any]:
        """Extract lead data from a single result card."""
        name = self._extract_business_name(card)
        if not name or name == "Unknown Business":
            return {}

        phone = self._extract_phone(card)
        address = self._extract_address(card)
        website = self._extract_website(card)

        location = (
            query.split()[-1]
            if " " in query
            else address.split(",")[-1].strip()
            if address
            else "Unknown"
        )

        raw_data = {
            "business_name": name,
            "phone": phone,
            "address": address,
            "website": website,
            "location": location,
        }

        return self.normalize_lead(raw_data, query=query)

    def _extract_business_name(self, card: Any) -> str:
        """Extract business name from card."""
        try:
            name_elem = card.query_selector(self.SELECTORS["business_name"])
            if name_elem:
                return name_elem.inner_text().strip()
        except Exception as e:
            self.log(f"Error extracting business name: {e}", "error")
        return "Unknown Business"

    def _extract_phone(self, card: Any) -> str | None:
        """Extract phone number from card."""
        try:
            phone_elem = card.query_selector(self.SELECTORS["phone"])
            if phone_elem:
                return phone_elem.inner_text().strip()
        except Exception as e:
            self.log(f"Error extracting phone: {e}", "error")
        return None

    def _extract_address(self, card: Any) -> str | None:
        """Extract address from card."""
        try:
            addr_elem = card.query_selector(self.SELECTORS["address"])
            if addr_elem:
                return addr_elem.inner_text().strip()
        except Exception as e:
            self.log(f"Error extracting address: {e}", "error")
        return None

    def _extract_website(self, card: Any) -> str | None:
        """Extract website from card."""
        try:
            web_elem = card.query_selector(self.SELECTORS["website"])
            if web_elem:
                href = web_elem.get_attribute("href")
                if href and href.startswith("http"):
                    return href
        except Exception as e:
            self.log(f"Error extracting website: {e}", "error")
        return None


ScraperRegistry.register(SulekhaScraper)
