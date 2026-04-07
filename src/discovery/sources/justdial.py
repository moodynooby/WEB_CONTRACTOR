"""JustDial scraper implementation."""

import time
from typing import Any, Dict, List

from playwright.sync_api import Page

from discovery.sources.base import BaseScraper, ScraperRegistry


class JustDialScraper(BaseScraper):
    """Scraper for JustDial business directory."""

    SOURCE_NAME = "justdial"
    BASE_URL = "https://www.justdial.com"

    SELECTORS = {
        "search_box": "input#global_where",
        "search_button": "button#global_search_btn",
        "results_container": "div#srchresl",
        "result_card": "li.rklw",
        "business_name": "span.cnm",
        "business_name_alt": "div.cnm > a",
        "phone": "span.mobilesv",
        "address": "span.add",
        "website": "a.mercweb",
        "next_button": "a.nxtpg",
    }

    def search(
        self, query: str, page: Page, max_results: int = 10
    ) -> List[Dict[str, Any]]:
        """Search JustDial for businesses matching query.

        Args:
            query: Search query (e.g., "web developers Mumbai")
            page: Playwright page object
            max_results: Maximum number of results to extract

        Returns:
            List of lead dictionaries
        """
        leads: List[Dict[str, Any]] = []

        try:
            search_url = f"{self.BASE_URL}/{query.replace(' ', '-')}"
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
                    lead = self._extract_lead_from_card(card, page, query)
                    if lead:
                        leads.append(lead)
                    if i < len(result_cards) - 1:
                        time.sleep(0.5)
                except Exception as e:
                    self.log(f"Error extracting lead from card: {e}", "error")
                    continue

        except Exception as e:
            self.log(f"Error searching JustDial: {e}", "error")

        return leads

    def _extract_lead_from_card(
        self,
        card: Any,
        page: Page,
        query: str,
    ) -> Dict[str, Any]:
        """Extract lead data from a single result card.

        Args:
            card: Result card element
            page: Playwright page object
            query: Original search query

        Returns:
            Lead dictionary or None if extraction failed
        """
        name = self._extract_business_name(card)
        if not name or name == "Unknown Business":
            return {}

        phone = self._extract_phone(card)
        address = self._extract_address(card)
        website = self._extract_website(card)
        listing_url = self._extract_listing_url(card)

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
            "listing_url": listing_url,
            "location": location,
        }

        lead = self.normalize_lead(raw_data, query=query)

        emails = self._extract_emails_from_page(page)
        if emails:
            lead["email"] = emails[0]

        return lead

    def _extract_business_name(self, card: Any) -> str:
        """Extract business name from card."""
        try:
            name_elem = card.query_selector(self.SELECTORS["business_name"])
            if name_elem:
                return name_elem.inner_text().strip()
            name_elem_alt = card.query_selector(self.SELECTORS["business_name_alt"])
            if name_elem_alt:
                return name_elem_alt.inner_text().strip()
        except Exception as e:
            self.log(f"Error extracting business name: {e}", "error")
        return "Unknown Business"

    def _extract_phone(self, card: Any) -> str | None:
        """Extract phone number from card."""
        try:
            phone_elem = card.query_selector(self.SELECTORS["phone"])
            if phone_elem:
                class_attr = phone_elem.get_attribute("class")
                if class_attr:
                    icon_class = class_attr.replace("mobilesv ", "")
                    phone_text = icon_class.replace("icon-", "").strip()
                    if phone_text:
                        return phone_text
                phone_class = phone_elem.get_attribute("class")
                if phone_class:
                    return phone_class
        except Exception as e:
            self.log(f"Error extracting phone: {e}", "error")

        try:
            phone_link = card.query_selector("a[href*='tel:']")
            if phone_link:
                href = phone_link.get_attribute("href")
                if href:
                    return href.replace("tel:", "").strip()
        except Exception as e:
            self.log(f"Error extracting phone from tel link: {e}", "error")

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
                if href and not href.startswith("javascript"):
                    if href.startswith("http"):
                        return href
                    if href.startswith("/"):
                        return f"{self.BASE_URL}{href}"
        except Exception as e:
            self.log(f"Error extracting website: {e}", "error")
        return None

    def _extract_listing_url(self, card: Any) -> str | None:
        """Extract the detail page URL for this listing."""
        try:
            link = card.query_selector("a[href*='/']")
            if link:
                href = link.get_attribute("href")
                if href:
                    if href.startswith("http"):
                        return href
                    if href.startswith("/"):
                        return f"{self.BASE_URL}{href}"
        except Exception as e:
            self.log(f"Error extracting listing URL: {e}", "error")
        return None


ScraperRegistry.register(JustDialScraper)
