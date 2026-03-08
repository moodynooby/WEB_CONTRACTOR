"""Discovery Module: Query Generation + Lead Scraping (Stage 0 + Stage A)

Single-threaded design with efficient resource management:
- Browser context reused across scraping operations
- Automatic cleanup on exit
- HTTP session for API calls
- Dynamic configuration from app_settings.json and database

Thread Safety:
- Playwright browser context is created per-thread using threading.local()
- Each scraping operation gets its own isolated browser context
- Context manager ensures proper cleanup even on exceptions
"""

import json
import random
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Dict, Generator, List, Optional

from playwright.sync_api import Page, sync_playwright

from core import llm
from core.db_peewee import (
    get_all_buckets, get_config,
    save_leads_batch,
)

_browser_context_local = threading.local()


def _load_app_settings() -> Dict:
    """Load application settings from config file."""
    settings_path = Path(__file__).parent.parent / "config" / "app_settings.json"
    try:
        with open(settings_path, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


class PlaywrightScraper:
    """Consolidated Stage 0 (Planning) + Stage A (Scraping)"""

    def __init__(
        self,
        logger: Optional[Callable] = None,
    ):
        self.buckets = get_all_buckets()
        self.logger = logger
        self._settings = _load_app_settings()

    @property
    def ollama_enabled(self) -> bool:
        return llm.is_available()

    def _get_llm_settings(self) -> Dict:
        """Get LLM settings from config."""
        defaults = {
            "default_model": "gemma:2b-instruct-q4_0",
            "expansion_model": "gemma:2b-instruct-q4_0",
            "timeout_seconds": 30,
            "max_retries": 2,
        }
        settings = self._settings.get("llm_settings", {})
        return {**defaults, **settings}

    def _get_discovery_limits(self) -> Dict:
        """Get discovery limits from config."""
        defaults = {
            "max_queries_per_run": 20,
            "max_patterns_per_bucket": 3,
            "max_cities_per_segment": 2,
            "max_results_per_query": 5,
            "max_leads_per_query": 2,
        }
        limits = self._settings.get("discovery_limits", {})
        return {**defaults, **limits}

    def _get_scraper_settings(self) -> Dict:
        """Get scraper settings from config."""
        defaults = {
            "headless": True,
            "user_agents": [
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            ],
            "page_load_timeout_ms": 5000,
            "search_wait_timeout_ms": 10000,
            "result_click_delay_ms": 2000,
        }
        settings = self._settings.get("scraper_settings", {})
        return {**defaults, **settings}

    def _get_random_user_agent(self) -> str:
        """Get a random user agent from configured list."""
        scraper_settings = self._get_scraper_settings()
        user_agents = scraper_settings["user_agents"]
        return random.choice(user_agents) if user_agents else user_agents[0]

    def log(self, message: str, style: str = "") -> None:
        """Log message to provided logger or print"""
        if self.logger:
            self.logger(message, style)
        else:
            print(message)

    @contextmanager
    def managed_session(self):
        """Context manager for scraping session - creates thread-local browser context
        
        Thread Safety:
        - Each thread gets its own browser context via threading.local()
        - Browser is launched once per thread and reused for all operations in that thread
        - Proper cleanup ensures no resource leaks
        """
        if hasattr(_browser_context_local, 'context') and _browser_context_local.context is not None:
            yield self
            return
        
        scraper_settings = self._get_scraper_settings()
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=scraper_settings["headless"])
            context = browser.new_context(
                user_agent=self._get_random_user_agent()
            )
            
            _browser_context_local.playwright = p
            _browser_context_local.browser = browser
            _browser_context_local.context = context
            
            try:
                yield self
            finally:
                context.close()
                browser.close()
                _browser_context_local.context = None
                _browser_context_local.browser = None
                _browser_context_local.playwright = None

    @contextmanager
    def get_page(self) -> Generator[Page, None, None]:
        """Context manager for page - uses current thread's context
        
        Thread Safety:
        - Uses thread-local storage to get the correct context for this thread
        - Raises RuntimeError if called outside managed_session()
        """
        if not hasattr(_browser_context_local, 'context') or _browser_context_local.context is None:
            raise RuntimeError("Scraper must be used within managed_session()")
        page = _browser_context_local.context.new_page()
        try:
            yield page
        finally:
            page.close()

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
            llm_settings = self._get_llm_settings()
            raw = llm.generate(
                model=llm_settings["expansion_model"],
                prompt=prompt,
                system="Output ONLY valid JSON. Market research assistant.",
                format_json=True,
                timeout=llm_settings["timeout_seconds"],
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
            llm_settings = self._get_llm_settings()
            raw = llm.generate(
                model=llm_settings["expansion_model"],
                prompt=prompt,
                system="Output ONLY valid JSON. Business strategist.",
                format_json=True,
                timeout=llm_settings["timeout_seconds"],
            )
            return json.loads(raw)
        except llm.OllamaError as e:
            self.log(f"Market discovery failed: {e}", "error")
            return None

    def generate_queries(
        self, bucket_name: Optional[str] = None, limit: Optional[int] = None
    ) -> List[Dict]:
        """Generate search queries from bucket patterns
        
        Args:
            bucket_name: Optional bucket name to filter queries
            limit: Optional limit override. If None, uses config or bucket default.
        """
        self.buckets = get_all_buckets()
        limits = self._get_discovery_limits()
        
        if limit is None:
            limit = limits["max_queries_per_run"]
        
        queries = []
        buckets = [
            b for b in self.buckets if not bucket_name or b["name"] == bucket_name
        ]
        
        buckets.sort(key=lambda b: b.get("priority", 1), reverse=True)

        geo_focus = get_config("geographic_focus") or {}

        for bucket in buckets:
            bucket_max_queries = bucket.get("max_queries", limits["max_patterns_per_bucket"])
            
            search_patterns = bucket.get("search_patterns", [])
            if isinstance(search_patterns, str):
                try:
                    search_patterns = json.loads(search_patterns)
                except json.JSONDecodeError as e:
                    self.log(f"Invalid JSON in search_patterns: {e}", "error")
                    search_patterns = []

            for pattern in search_patterns[:bucket_max_queries]:
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
                        max_cities = limits["max_cities_per_segment"]
                        cities.extend(geo_focus[seg_name].get("cities", [])[:max_cities])

                if not cities:
                    self.log(
                        f"No cities found for bucket '{bucket['name']}' pattern '{pattern}'. "
                        f"Configure geographic_focus in settings.",
                        "error",
                    )
                    continue

                for city in cities:
                    query = pattern.replace("{city}", city)
                    queries.append(
                        {"query": query, "bucket": bucket["name"], "city": city}
                    )
                    if len(queries) >= limit:
                        return queries

        return queries[:limit]

    def scrape_google_maps(
        self, query: str, bucket: str, max_results: Optional[int] = None
    ) -> List[Dict]:
        """Scrape Google Maps for business leads using Playwright
        
        Args:
            query: Search query
            bucket: Bucket name
            max_results: Optional max results override. If None, uses config.
        """
        leads: List[Dict] = []
        scraper_settings = self._get_scraper_settings()
        limits = self._get_discovery_limits()
        
        if max_results is None:
            max_results = limits["max_results_per_query"]

        with self.get_page() as page:
            try:
                search_url = (
                    f"https://www.google.com/maps/search/{query.replace(' ', '+')}"
                )
                page.goto(search_url)
                page.wait_for_timeout(scraper_settings["page_load_timeout_ms"])

                try:
                    page.wait_for_selector(
                        "a[href*='/maps/place/']", 
                        timeout=scraper_settings["search_wait_timeout_ms"]
                    )
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
                        page.wait_for_timeout(scraper_settings["result_click_delay_ms"])

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

    def _scrape_query(self, query_data: Dict) -> List[Dict]:
        """Scrape a single query across all sources sequentially to ensure thread-safety."""
        query = query_data["query"]
        bucket = query_data["bucket"]
        query_leads: List[Dict] = []
        
        bucket_data = next((b for b in self.buckets if b["name"] == bucket), None)
        max_results = bucket_data.get("max_results") if bucket_data else None
        
        query_leads.extend(self.scrape_google_maps(query, bucket, max_results=max_results))

        return query_leads

    def run(
        self,
        bucket_name: Optional[str] = None,
        max_queries: Optional[int] = None,
    ) -> Dict:
        """Execute full discovery pipeline - single-threaded with efficient resource reuse
        
        Args:
            bucket_name: Optional bucket name to filter queries
            max_queries: Optional max queries override. If None, uses config or bucket default.
        """
        self.buckets = self._load_buckets()
        limits = self._get_discovery_limits()
        
        if max_queries is None:
            max_queries = limits["max_queries_per_run"]
        
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
