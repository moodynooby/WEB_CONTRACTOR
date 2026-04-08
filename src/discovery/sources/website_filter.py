"""Website filter scraper for broad website discovery."""

from typing import Any, Dict, List

from playwright.sync_api import Page

from discovery.sources.base import BaseScraper, ScraperRegistry


class WebsiteFilterScraper(BaseScraper):
    """Scraper for broad website discovery using site filters.

    Searches Google with site: filters for various TLDs to discover
    business websites across all domains.
    """

    SOURCE_NAME = "website_filter"
    BASE_URL = "https://www.google.com/search"

    SITE_FILTERS = [
        ".com",
        ".in",
        ".co.in",
        ".org",
        ".co",
        ".io",
        ".net",
        ".biz",
        ".info",
    ]

    SELECTORS = {
        "result_container": "div.g",
        "result_link": "a",
        "result_title": "h3",
        "result_snippet": "div[data-sncf], span.aCOpRe, div.VwiC3b",
    }

    def search(
        self, query: str, page: Page, max_results: int = 5
    ) -> List[Dict[str, Any]]:
        """Search for business websites using site filters.

        Args:
            query: Search query (e.g., "web developers Mumbai")
            page: Playwright page object
            max_results: Maximum number of results to extract

        Returns:
            List of lead dictionaries
        """
        leads: List[Dict[str, Any]] = []

        for tld in self.SITE_FILTERS:
            try:
                site_leads = self._search_tld(
                    query, page, tld, max_results
                )
                leads.extend(site_leads)
            except Exception as e:
                self.log(f"Error searching {tld}: {e}", "error")
                continue

        return leads

    def _search_tld(
        self, query: str, page: Page, tld: str, max_results: int
    ) -> List[Dict[str, Any]]:
        """Search for a specific TLD.

        Args:
            query: Base search query
            page: Playwright page object
            tld: TLD to search for (e.g., ".com", ".in")
            max_results: Max results to extract

        Returns:
            List of lead dictionaries
        """
        leads: List[Dict[str, Any]] = []

        search_query = f"{query} site:{tld}"
        encoded_query = search_query.replace(" ", "+")

        try:
            search_url = f"{self.BASE_URL}?q={encoded_query}"
            page.goto(search_url, wait_until="domcontentloaded")
            page.wait_for_timeout(self.settings.get("page_load_timeout_ms", 3000))

            results = page.query_selector_all(
                self.SELECTORS["result_container"]
            )
            results = results[:max_results]

            for result in results:
                try:
                    lead = self._extract_lead(result, query, page, tld)
                    if lead:
                        leads.append(lead)
                except Exception as e:
                    self.log(f"Error extracting lead: {e}", "error")
                    continue

        except Exception as e:
            self.log(f"Error searching {tld}: {e}", "error")

        return leads

    def _extract_lead(
        self, element: Any, query: str, page: Page, tld: str
    ) -> Dict[str, Any] | None:
        """Extract lead data from a search result.

        Args:
            element: Result element
            query: Original search query
            page: Playwright page object
            tld: TLD that was searched

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
            if not url or not url.startswith("http"):
                return None

            url = self._normalize_url(url)
            if not url:
                return None

            title = title_elem.inner_text() if title_elem else ""
            snippet = snippet_elem.inner_text() if snippet_elem else ""

            try:
                page.goto(url, wait_until="domcontentloaded", timeout=5000)
                page.wait_for_timeout(2000)

                emails = self._extract_emails_from_page(page)
                phones = self._extract_phones_from_page(page)
            except Exception:
                emails = []
                phones = []

            location = query.split()[-1] if " " in query else ""

            raw_data = {
                "business_name": title or url,
                "website": url,
                "phone": phones[0] if phones else None,
                "email": emails[0] if emails else None,
                "location": location,
                "listing_url": url,
                "snippet": snippet,
                "tld": tld,
            }

            return self.normalize_lead(raw_data, query=query)

        except Exception as e:
            self.log(f"Error extracting website lead: {e}", "error")
            return None


ScraperRegistry.register(WebsiteFilterScraper)
