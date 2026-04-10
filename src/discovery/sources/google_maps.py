"""Google Maps scraper for business listings.

Uses Playwright to navigate Google Maps and extract:
- Business names
- Website URLs
- Phone numbers
- Addresses

Note: This scraper relies on Google Maps UI which may change frequently.
"""

from typing import Any, Dict, List

from playwright.sync_api import Page

from discovery.sources.base import BaseScraper, ScraperRegistry


class GoogleMapsScraper(BaseScraper):
    """Scraper for Google Maps business listings."""

    SOURCE_NAME = "google_maps"
    BASE_URL = "https://www.google.com/maps"

    SELECTORS = {
        "search_box": "input#searchboxinput",
        "search_button": "button#searchbox-searchbutton",
        "results_container": "div[role='feed']",
        "result_link": "a[href*='/maps/place/']",
        "business_name": "h1.DUwDvf",
        "website": "a[data-item-id*='authority']",
        "phone": "button[data-item-id*='phone']",
        "address": "button[data-item-id*='address']",
        "next_button": "button[aria-label='Next']",
    }

    def search(
        self, query: str, page: Page, max_results: int = 5
    ) -> List[Dict[str, Any]]:
        """Search Google Maps for businesses matching query.

        Args:
            query: Search query (e.g., "web developers Mumbai")
            page: Playwright page object
            max_results: Maximum number of results to extract

        Returns:
            List of lead dictionaries
        """
        leads: List[Dict[str, Any]] = []

        try:
            search_url = f"{self.BASE_URL}/search/{query.replace(' ', '+')}"
            page.goto(search_url, wait_until="domcontentloaded")
            page.wait_for_timeout(self.settings.get("page_load_timeout_ms", 5000))

            try:
                page.wait_for_selector(
                    self.SELECTORS["result_link"],
                    timeout=self.settings.get("search_wait_timeout_ms", 10000),
                )
            except Exception:
                self.log(f"No results found for query: {query}", "error")
                return leads

            business_elements = page.query_selector_all(self.SELECTORS["result_link"])
            business_elements = business_elements[:max_results]

            for element in business_elements:
                try:
                    lead = self._extract_lead_from_element(page, element, query)
                    if lead:
                        leads.append(lead)
                except Exception as e:
                    self.log(f"Error extracting lead: {e}", "error")
                    continue

        except Exception as e:
            self.log(f"Error searching Google Maps: {e}", "error")

        return leads

    def _extract_lead_from_element(
        self,
        page: Page,
        element: Any,
        query: str,
    ) -> Dict[str, Any]:
        """Extract lead data from a single business element.

        Args:
            page: Playwright page object
            element: Business element to extract from
            query: Original search query

        Returns:
            Lead dictionary or None if extraction failed
        """
        try:
            element.click()
            page.wait_for_timeout(self.settings.get("result_click_delay_ms", 2000))
        except Exception as e:
            self.log(f"Error clicking business element: {e}", "error")
            return {}

        name = self._extract_business_name(page)
        website = self._extract_website(page)
        phone = self._extract_phone(page)
        address = self._extract_address(page)

        location = query.split()[-1] if " " in query else "Unknown"

        raw_data = {
            "business_name": name,
            "website": website,
            "phone": phone,
            "address": address,
            "location": location,
        }

        return self.normalize_lead(raw_data, query=query)

    def _extract_business_name(self, page: Page) -> str:
        """Extract business name from detail page."""
        try:
            name_elem = page.query_selector(self.SELECTORS["business_name"])
            if name_elem:
                return name_elem.inner_text()
        except Exception as e:
            self.log(f"Error extracting business name: {e}", "error")
        return "Unknown Business"

    def _extract_website(self, page: Page) -> str | None:
        """Extract website URL from detail page."""
        try:
            website_elem = page.query_selector(self.SELECTORS["website"])
            if website_elem:
                href = website_elem.get_attribute("href")
                if href:
                    parsed = href.split("&")[0]
                    if parsed.startswith("http"):
                        return parsed
                    if parsed.startswith("/url?"):
                        from urllib.parse import parse_qs, urlparse

                        params = parse_qs(urlparse(parsed).query)
                        if "q" in params:
                            return params["q"][0]
        except Exception as e:
            self.log(f"Error extracting website: {e}", "error")
        return None

    def _extract_phone(self, page: Page) -> str | None:
        """Extract phone number from detail page."""
        try:
            phone_elem = page.query_selector(self.SELECTORS["phone"])
            if phone_elem:
                aria_label = phone_elem.get_attribute("aria-label")
                if aria_label:
                    return aria_label.replace("Phone: ", "").strip()
        except Exception as e:
            self.log(f"Error extracting phone: {e}", "error")
        return None

    def _extract_address(self, page: Page) -> str | None:
        """Extract address from detail page."""
        try:
            address_elem = page.query_selector(self.SELECTORS["address"])
            if address_elem:
                aria_label = address_elem.get_attribute("aria-label")
                if aria_label:
                    return aria_label.replace("Address: ", "").strip()
        except Exception as e:
            self.log(f"Error extracting address: {e}", "error")
        return None


ScraperRegistry.register(GoogleMapsScraper)
