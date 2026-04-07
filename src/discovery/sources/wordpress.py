"""WordPress.com scraper for finding business blogs."""

from typing import Any, Dict, List

from playwright.sync_api import Page

from discovery.sources.base import BaseScraper, ScraperRegistry


class WordPressScraper(BaseScraper):
    """Scraper for WordPress.com hosted sites."""

    SOURCE_NAME = "wordpress"
    BASE_URL = "https://wordpress.com"

    SELECTORS = {
        "search_url": "https://www.google.com/search?q=site:wordpress.com+{query}",
        "result_container": "div.g",
        "result_link": "a",
        "result_title": "h3",
        "result_snippet": "div[data-sncf], span.aCOpRe, div.VwiC3b",
    }

    def search(
        self, query: str, page: Page, max_results: int = 5
    ) -> List[Dict[str, Any]]:
        """Search for WordPress.com sites matching the query.

        Args:
            query: Search query (e.g., "web developers Mumbai")
            page: Playwright page object
            max_results: Maximum number of results to extract

        Returns:
            List of lead dictionaries
        """
        leads: List[Dict[str, Any]] = []

        search_url = self.SELECTORS["search_url"].format(
            query=query.replace(" ", "+")
        )

        try:
            page.goto(search_url, wait_until="domcontentloaded")
            page.wait_for_timeout(self.settings.get("page_load_timeout_ms", 3000))

            results = page.query_selector_all(
                self.SELECTORS["result_container"]
            )
            results = results[:max_results]

            for result in results:
                try:
                    lead = self._extract_lead(result, query, page)
                    if lead:
                        leads.append(lead)
                except Exception as e:
                    self.log(f"Error extracting lead: {e}", "error")
                    continue

        except Exception as e:
            self.log(f"Error searching WordPress: {e}", "error")

        return leads

    def _extract_lead(
        self, element: Any, query: str, page: Page
    ) -> Dict[str, Any]:
        """Extract lead data from a search result.

        Args:
            element: Result element
            query: Original search query
            page: Playwright page object

        Returns:
            Lead dictionary or None
        """
        try:
            link_elem = element.query_selector(self.SELECTORS["result_link"])
            title_elem = element.query_selector(self.SELECTORS["result_title"])
            snippet_elem = element.query_selector(
                self.SELECTORS["result_snippet"]
            )

            if not link_elem:
                return None

            url = link_elem.get_attribute("href")
            if not url or "wordpress.com" not in url:
                return None

            url = self._normalize_url(url)
            if not url:
                return None

            title = title_elem.inner_text() if title_elem else ""
            snippet = snippet_elem.inner_text() if snippet_elem else ""

            page.goto(url, wait_until="domcontentloaded", timeout=5000)
            page.wait_for_timeout(2000)

            emails = self._extract_emails_from_page(page)
            phones = self._extract_phones_from_page(page)

            location = query.split()[-1] if " " in query else ""

            raw_data = {
                "business_name": title or url,
                "website": url,
                "phone": phones[0] if phones else None,
                "email": emails[0] if emails else None,
                "location": location,
                "listing_url": url,
                "snippet": snippet,
            }

            return self.normalize_lead(raw_data, query=query)

        except Exception as e:
            self.log(f"Error extracting WordPress lead: {e}", "error")
            return None


ScraperRegistry.register(WordPressScraper)
