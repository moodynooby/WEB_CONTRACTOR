"""Discovery Module: Query Generation + Lead Scraping (Stage 0 + Stage A)

Single-threaded design with efficient resource management:
- Browser context reused across scraping operations
- Automatic cleanup on exit
- HTTP session reuse for API calls
"""

import json
from contextlib import contextmanager
from typing import Callable, Dict, Generator, List, Optional

from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright

from core import llm
from core.db_peewee import (
    get_all_buckets, get_config,
    save_leads_batch,
)




class PlaywrightScraper:
    """Consolidated Stage 0 (Planning) + Stage A (Scraping)"""

    def __init__(
        self,
        logger: Optional[Callable] = None,
    ):
        self.buckets = get_all_buckets()
        self.logger = logger

        self._playwright: Optional[sync_playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None

    @property
    def ollama_enabled(self) -> bool:
        return llm.is_available()

    def log(self, message: str, style: str = "") -> None:
        """Log message to provided logger or print"""
        if self.logger:
            self.logger(message, style)
        else:
            print(message)

    def _ensure_browser(self) -> Browser:
        """Ensure browser is initialized (lazy loading)"""
        if self._playwright is None:
            self._playwright = sync_playwright().start()
        if self._browser is None:
            self._browser = self._playwright.chromium.launch(headless=True)
        return self._browser

    def _ensure_context(self) -> BrowserContext:
        """Ensure browser context is initialized (reused across calls)"""
        browser = self._ensure_browser()
        if self._context is None:
            self._context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )
        return self._context

    @contextmanager
    def get_page(self) -> Generator[Page, None, None]:
        """Context manager for page - creates new page, yields it, closes after use"""
        context = self._ensure_context()
        page = context.new_page()
        try:
            yield page
        finally:
            page.close()

    def close_all(self) -> None:
        """Close all Playwright resources (call once at end of session)"""
        if self._context:
            try:
                self._context.close()
            except Exception:
                pass
            self._context = None
        if self._browser:
            try:
                self._browser.close()
            except Exception:
                pass
            self._browser = None
        if self._playwright:
            try:
                self._playwright.stop()
            except Exception:
                pass
            self._playwright = None

    @contextmanager
    def managed_session(self):
        """Context manager for full scraping session - ensures cleanup"""
        try:
            yield self
        finally:
            self.close_all()

    def _load_buckets(self) -> List[Dict]:
        """Load bucket configuration from DB"""
        return get_all_buckets()

    def expand_bucket(self, bucket_name: str) -> Optional[Dict]:
        """Use LLM to expand bucket categories and search patterns."""
        if not self.ollama_enabled:
            return None

        bucket = next((b for b in self.buckets if b["name"] == bucket_name), None)
        if not bucket:
            return None

        self.log(f"Expanding bucket: {bucket_name} using LLM...", "info")

        prompt = f"""Bucket: {bucket_name}
Cats: {bucket.get("categories", [])}
Patterns: {bucket.get("search_patterns", [])}

Suggest:
1. 3 new categories
2. 3 new search patterns with '{{city}}'
3. 2 new target cities in India

Return ONLY JSON:
{{"new_categories": ["c1", "c2"], "new_patterns": ["p1 {{city}}"], "new_cities": ["City1"]}}"""

        try:
            raw = llm.generate(
                model="gemma:2b-instruct-q4_0",
                prompt=prompt,
                system="Output ONLY valid JSON. Market research assistant.",
                format_json=True,
                timeout=30,
            )
            return json.loads(raw)
        except llm.OllamaError as e:
            self.log(f"Expansion failed: {e}", "error")
            return None

    def discover_new_buckets(self) -> Optional[List[Dict]]:
        """Use LLM to suggest new market buckets based on current ones."""
        if not self.ollama_enabled:
            return None

        self.log("Discovering new market opportunities using LLM...", "info")

        current_buckets = [b["name"] for b in self.buckets]

        prompt = f"""Current Buckets: {current_buckets}

Suggest 2 new industries for web dev services.
Provide:
- Name
- 2 categories
- 2 patterns with '{{city}}'

Return ONLY JSON list:
[{{"name": "Market", "categories": ["c1", "c2"], "search_patterns": ["p1 {{city}}"]}}]"""

        try:
            raw = llm.generate(
                model="gemma:2b-instruct-q4_0",
                prompt=prompt,
                system="Output ONLY valid JSON. Business strategist.",
                format_json=True,
                timeout=30,
            )
            return json.loads(raw)
        except llm.OllamaError as e:
            self.log(f"Market discovery failed: {e}", "error")
            return None

    def generate_queries(
        self, bucket_name: Optional[str] = None, limit: int = 20
    ) -> List[Dict]:
        """Generate search queries from bucket patterns"""
        self.buckets = get_all_buckets()
        queries = []
        buckets = [
            b for b in self.buckets if not bucket_name or b["name"] == bucket_name
        ]

        geo_focus = get_config("geographic_focus") or {}

        for bucket in buckets:
            search_patterns = bucket.get("search_patterns", [])
            if isinstance(search_patterns, str):
                try:
                    search_patterns = json.loads(search_patterns)
                except json.JSONDecodeError as e:
                    self.log(f"Invalid JSON in search_patterns: {e}", "error")
                    search_patterns = []

            for pattern in search_patterns[:3]:
                cities = []
                segments = bucket.get("geographic_segments", [])
                if isinstance(segments, str):
                    try:
                        segments = json.loads(segments)
                    except json.JSONDecodeError as e:
                        self.log(f"Invalid JSON in geographic_segments: {e}", "error")
                        segments = []

                if not segments:
                    segments = ["tier_1_metros"]

                for seg_name in segments:
                    if seg_name in geo_focus:
                        cities.extend(geo_focus[seg_name].get("cities", [])[:2])

                if not cities:
                    self.log(
                        f"No cities found for bucket '{bucket['name']}' pattern '{pattern}'. "
                        f"Configure geographic_focus in settings.",
                        "error",
                    )
                    continue

                for city in cities[:2]:
                    query = pattern.replace("{city}", city)
                    queries.append(
                        {"query": query, "bucket": bucket["name"], "city": city}
                    )
                    if len(queries) >= limit:
                        return queries

        return queries[:limit]

    def scrape_google_maps(
        self, query: str, bucket: str, max_results: int = 5
    ) -> List[Dict]:
        """Scrape Google Maps for business leads using Playwright"""
        leads: List[Dict] = []

        with self.get_page() as page:
            try:
                search_url = (
                    f"https://www.google.com/maps/search/{query.replace(' ', '+')}"
                )
                page.goto(search_url)
                page.wait_for_timeout(3000)

                try:
                    page.wait_for_selector("a[href*='/maps/place/']", timeout=10000)
                except Exception:
                    self.log(
                        f"Google Maps search results not loaded for query '{query}'",
                        "error",
                    )
                    return leads

                business_elements = page.query_selector_all("a[href*='/maps/place/']")
                business_elements = business_elements[:max_results]

                for element in business_elements:
                    try:
                        element.click()
                        page.wait_for_timeout(2000)

                        try:
                            name_elem = page.query_selector("h1.DUwDvf")
                            name = (
                                name_elem.inner_text()
                                if name_elem
                                else "Unknown Business"
                            )
                        except Exception as e:
                            self.log(
                                f"Unexpected error finding business name: {e}", "error"
                            )
                            name = "Unknown Business"

                        website = None
                        try:
                            website_elem = page.query_selector(
                                "a[data-item-id*='authority']"
                            )
                            website = (
                                website_elem.get_attribute("href")
                                if website_elem
                                else None
                            )
                        except Exception as e:
                            self.log(
                                f"Error extracting website from Google Maps: {e}",
                                "error",
                            )

                        phone = None
                        try:
                            phone_elem = page.query_selector(
                                "button[data-item-id*='phone']"
                            )
                            phone = (
                                phone_elem.get_attribute("aria-label")
                                if phone_elem
                                else None
                            )
                        except Exception as e:
                            self.log(
                                f"Error extracting phone from Google Maps: {e}", "error"
                            )

                        if name:
                            leads.append(
                                {
                                    "business_name": name,
                                    "website": website,
                                    "phone": phone,
                                    "source": "google_maps",
                                    "bucket": bucket,
                                    "category": query.split()[0],
                                    "location": query.split()[-1]
                                    if " " in query
                                    else "Unknown",
                                }
                            )

                    except Exception:
                        continue

            except Exception as e:
                self.log(f"Error scraping Google Maps: {e}", "error")

        return leads

    def scrape_justdial(
        self, query: str, bucket: str, max_results: int = 5
    ) -> List[Dict]:
        """Scrape JustDial for Indian business leads using Playwright"""
        leads: List[Dict] = []

        with self.get_page() as page:
            try:
                query_parts = query.split()
                city = query_parts[-1] if len(query_parts) > 1 else "Mumbai"
                search_term = (
                    " ".join(query_parts[:-1]) if len(query_parts) > 1 else query
                )
                search_url = (
                    f"https://www.justdial.com/{city}/{search_term.replace(' ', '-')}"
                )

                page.goto(search_url)
                page.wait_for_timeout(3000)

                try:
                    page.wait_for_selector(".jsx-1e1a185d7f5319c2", timeout=10000)
                except Exception:
                    self.log(
                        f"JustDial search results not loaded for query '{query}'",
                        "error",
                    )
                    return leads

                business_elements = page.query_selector_all(".jsx-1e1a185d7f5319c2")
                business_elements = business_elements[:max_results]

                for element in business_elements:
                    try:
                        try:
                            name_elem = element.query_selector(".jsx-2c8ae8c8b6b8b1b0")
                            name = (
                                name_elem.inner_text().strip()
                                if name_elem
                                else "Unknown Business"
                            )
                        except Exception:
                            name = "Unknown Business"

                        phone = None
                        try:
                            phone_elem = element.query_selector(".jsx-3c8ae8c8b6b8b1b0")
                            phone = (
                                phone_elem.inner_text().strip() if phone_elem else None
                            )
                        except Exception as e:
                            self.log(
                                f"Error extracting phone from JustDial: {e}", "error"
                            )

                        website = None
                        try:
                            website_elem = element.query_selector("a[href*='http']")
                            website = (
                                website_elem.get_attribute("href")
                                if website_elem
                                else None
                            )
                        except Exception as e:
                            self.log(
                                f"Error extracting website from JustDial: {e}", "error"
                            )

                        if name:
                            leads.append(
                                {
                                    "business_name": name,
                                    "website": website,
                                    "phone": phone,
                                    "source": "justdial",
                                    "bucket": bucket,
                                    "category": search_term.split()[0],
                                    "location": city,
                                }
                            )

                    except Exception:
                        continue

            except Exception as e:
                self.log(f"Error scraping JustDial: {e}", "error")

        return leads

    def scrape_indiamart(
        self, query: str, bucket: str, max_results: int = 5
    ) -> List[Dict]:
        """Scrape IndiaMART for B2B business leads using Playwright"""
        leads: List[Dict] = []

        with self.get_page() as page:
            try:
                search_url = f"https://dir.indiamart.com/search.mp?search={query.replace(' ', '+')}"
                page.goto(search_url)
                page.wait_for_timeout(3000)

                try:
                    page.wait_for_selector(".pbox", timeout=10000)
                except Exception:
                    self.log(
                        f"IndiaMART search results not loaded for query '{query}'",
                        "error",
                    )
                    return leads

                business_elements = page.query_selector_all(".pbox")
                business_elements = business_elements[:max_results]

                for element in business_elements:
                    try:
                        try:
                            name_elem = element.query_selector(".lst_clg a")
                            name = (
                                name_elem.inner_text().strip()
                                if name_elem
                                else "Unknown Business"
                            )
                        except Exception:
                            name = "Unknown Business"

                        website = None
                        try:
                            website_elem = element.query_selector(".lst_clg a")
                            website = (
                                website_elem.get_attribute("href")
                                if website_elem
                                else None
                            )
                        except Exception as e:
                            self.log(
                                f"Error extracting website from IndiaMART: {e}", "error"
                            )

                        phone = None
                        try:
                            phone_elem = element.query_selector(".pnum")
                            phone = (
                                phone_elem.inner_text().strip() if phone_elem else None
                            )
                        except Exception as e:
                            self.log(
                                f"Error extracting phone from IndiaMART: {e}", "error"
                            )

                        if name:
                            leads.append(
                                {
                                    "business_name": name,
                                    "website": website,
                                    "phone": phone,
                                    "source": "indiamart",
                                    "bucket": bucket,
                                    "category": query.split()[0],
                                    "location": "India",
                                }
                            )

                    except Exception as e:
                        self.log(f"Error processing IndiaMART listing: {e}", "error")
                        continue

            except Exception as e:
                self.log(
                    f"Error scraping IndiaMART - query='{query}', bucket='{bucket}': {e}",
                    "error",
                )

        return leads

    def scrape_yelp(self, query: str, bucket: str, max_results: int = 5) -> List[Dict]:
        """Scrape Yelp for business leads using Playwright"""
        leads: List[Dict] = []

        with self.get_page() as page:
            try:
                search_url = (
                    f"https://www.yelp.com/search?find_desc={query.replace(' ', '+')}"
                )
                page.goto(search_url)
                page.wait_for_timeout(3000)

                try:
                    page.wait_for_selector(".container__09f24__mpRFF", timeout=10000)
                except Exception:
                    self.log(
                        f"Yelp search results not loaded for query '{query}'", "error"
                    )
                    return leads

                business_elements = page.query_selector_all(".container__09f24__mpRFF")
                business_elements = business_elements[:max_results]

                for element in business_elements:
                    try:
                        try:
                            name_elem = element.query_selector("a[href*='/biz/']")
                            name = (
                                name_elem.inner_text().strip()
                                if name_elem
                                else "Unknown Business"
                            )
                        except Exception:
                            name = "Unknown Business"

                        website = None
                        try:
                            website_elem = element.query_selector("a[href*='biz/']")
                            website = (
                                website_elem.get_attribute("href")
                                if website_elem
                                else None
                            )
                        except Exception as e:
                            self.log(
                                f"Error extracting website from Yelp: {e}", "error"
                            )

                        phone = None
                        try:
                            phone_elem = element.query_selector(".phone__09f24__pARZf")
                            phone = (
                                phone_elem.inner_text().strip() if phone_elem else None
                            )
                        except Exception as e:
                            self.log(f"Error extracting phone from Yelp: {e}", "error")

                        if name:
                            leads.append(
                                {
                                    "business_name": name,
                                    "website": website,
                                    "phone": phone,
                                    "source": "yelp",
                                    "bucket": bucket,
                                    "category": query.split()[0],
                                    "location": "International",
                                }
                            )

                    except Exception as e:
                        self.log(f"Error processing Yelp listing: {e}", "error")
                        continue

            except Exception as e:
                self.log(
                    f"Error scraping Yelp - query='{query}', bucket='{bucket}': {e}",
                    "error",
                )

        return leads

    def _scrape_query(self, query_data: Dict) -> List[Dict]:
        """Scrape a single query across all sources (for parallel execution)"""
        query = query_data["query"]
        bucket = query_data["bucket"]

        query_leads: List[Dict] = []

        query_leads.extend(self.scrape_google_maps(query, bucket, max_results=2))

        if len(query_leads) < 3:
            query_leads.extend(
                self.scrape_justdial(query, bucket, 3 - len(query_leads))
            )

        if len(query_leads) < 3:
            query_leads.extend(
                self.scrape_indiamart(query, bucket, 3 - len(query_leads))
            )

        if len(query_leads) < 3:
            query_leads.extend(self.scrape_yelp(query, bucket, 3 - len(query_leads)))

        return query_leads

    def run(
        self,
        bucket_name: Optional[str] = None,
        max_queries: int = 5,
    ) -> Dict:
        """Execute full discovery pipeline - single-threaded with efficient resource reuse"""
        self.buckets = self._load_buckets()
        self.log(f"\n{'=' * 60}")
        self.log("DISCOVERY: Query Generation + Lead Scraping")
        self.log(f"{'=' * 60}")

        queries = self.generate_queries(bucket_name, max_queries)
        self.log(f"Generated {len(queries)} search queries", "info")

        total_leads = 0
        total_saved = 0

        with self.managed_session():
            for i, q in enumerate(queries, 1):
                self.log(f"\n[{i}/{len(queries)}] {q['query']}", "info")

                query_leads = self._scrape_query(q)

                if query_leads:
                    saved = save_leads_batch(query_leads)
                    total_saved += saved
                    total_leads += len(query_leads)
                    self.log(
                        f"  Found {len(query_leads)} leads, saved {saved}",
                        "success",
                    )

        self.log(f"\n{'=' * 60}")
        self.log(
            f"Discovery Complete: {total_leads} found, {total_saved} saved", "success"
        )
        self.log(f"{'=' * 60}\n")

        return {
            "queries_executed": len(queries),
            "leads_found": total_leads,
            "leads_saved": total_saved,
        }
