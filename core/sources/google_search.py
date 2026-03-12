"""Google Search scraper for finding websites on blog platforms."""

from typing import Any, Dict, List

from playwright.sync_api import Page

from core.sources.base import BaseScraper, ScraperRegistry


class GoogleSearchScraper(BaseScraper):
    """Scraper for Google Search results targeting blog platforms."""

    SOURCE_NAME = "google_search"
    BASE_URL = "https://www.google.com/search"

    BLOG_PLATFORMS = [
        "blogspot.com",
        "wordpress.com",
        "wix.com",
        "squarespace.com",
        "weebly.com",
        "shopify.com",
    ]

    SELECTORS = {
        "result_container": "div.g",
        "result_link": "a",
        "result_title": "h3",
        "result_snippet": "div[data-sncf]",
        "next_button": "button#pnnext",
    }

    def search(
        self, query: str, page: Page, max_results: int = 5
    ) -> List[Dict[str, Any]]:
        """Search Google for businesses on blog platforms.

        Args:
            query: Search query (e.g., "web developers Mumbai")
            page: Playwright page object
            max_results: Maximum number of results to extract per platform

        Returns:
            List of lead dictionaries
        """
        leads: List[Dict[str, Any]] = []

        for platform in self.BLOG_PLATFORMS:
            try:
                platform_leads = self._search_platform(
                    query, page, platform, max_results
                )
                leads.extend(platform_leads)
            except Exception as e:
                self.log(f"Error searching {platform}: {e}", "error")
                continue

        return leads

    def _search_platform(
        self, query: str, page: Page, platform: str, max_results: int
    ) -> List[Dict[str, Any]]:
        """Search Google for a specific platform.

        Args:
            query: Base search query
            page: Playwright page object
            platform: Platform domain (e.g., "blogspot.com")
            max_results: Max results to extract

        Returns:
            List of lead dictionaries
        """
        leads: List[Dict[str, Any]] = []

        search_query = f"{query} site:{platform}"
        encoded_query = search_query.replace(" ", "+")

        try:
            search_url = f"{self.BASE_URL}?q={encoded_query}"
            page.goto(search_url, wait_until="domcontentloaded")
            page.wait_for_timeout(self.settings.get("page_load_timeout_ms", 3000))

            results = page.query_selector_all(self.SELECTORS["result_container"])
            results = results[:max_results]

            for result in results:
                try:
                    lead = self._extract_lead_from_element(result, query, platform)
                    if lead:
                        leads.append(lead)
                except Exception as e:
                    self.log(f"Error extracting lead: {e}", "error")
                    continue

        except Exception as e:
            self.log(f"Error searching {platform}: {e}", "error")

        return leads

    def _extract_lead_from_element(
        self, element: Any, query: str, platform: str
    ) -> Dict[str, Any]:
        """Extract lead data from a single search result element.

        Args:
            element: Result element to extract from
            query: Original search query
            platform: Platform domain (e.g., "blogspot.com")

        Returns:
            Lead dictionary or None
        """
        try:
            link_elem = element.query_selector(self.SELECTORS["result_link"])
            title_elem = element.query_selector(self.SELECTORS["result_title"])
            snippet_elem = element.query_selector(self.SELECTORS["result_snippet"])

            if not link_elem:
                return None

            url = link_elem.get_attribute("href")
            if not url or not url.startswith("http"):
                return None

            title = title_elem.inner_text() if title_elem else ""
            snippet = snippet_elem.inner_text() if snippet_elem else ""

            location = query.split()[-1] if " " in query else ""

            raw_data = {
                "business_name": title or url,
                "website": url,
                "phone": None,
                "email": None,
                "location": location,
                "listing_url": url,
                "platform": platform,
                "title": title,
                "snippet": snippet,
            }

            return self.normalize_lead(raw_data, query=query)

        except Exception as e:
            self.log(f"Error extracting lead data: {e}", "error")
            return None


ScraperRegistry.register(GoogleSearchScraper)
