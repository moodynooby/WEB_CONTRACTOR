"""Discovery Module: Query Generation + Lead Scraping (Stage 0 + Stage A)

Efficient resource management with per-operation browser contexts:
- Fresh browser context created for each scraping operation
- Automatic cleanup on exit via context managers
- HTTP session for API calls
- Dynamic configuration from app_settings.json and database
"""

import asyncio
import json
import random
from contextlib import contextmanager
from typing import Any, Callable, Dict, Generator, List, Optional, Tuple

from playwright.sync_api import Page, sync_playwright

from core import llm
from core.utils import load_json_config
from core.db_repository import (
    get_all_buckets,
    get_bucket_id_by_name,
    save_leads_batch,
    get_or_create_query_performance,
    update_query_performance,
    mark_query_as_stale,
    get_stale_queries,
    cleanup_stale_queries,
)
from core.sources import get_all_enabled_sources


def _load_app_settings() -> dict:
    """Load application settings from config file."""
    return load_json_config("app_settings.json")


class PlaywrightScraper:
    """Consolidated Stage 0 (Planning) + Stage A (Scraping)"""

    def __init__(
        self,
        logger: Callable | None = None,
    ):
        self.buckets = get_all_buckets()
        self.logger = logger
        self._settings = load_json_config("app_settings.json")

    @property
    def ollama_enabled(self) -> bool:
        return llm.is_available()

    def _get_llm_settings(self) -> dict:
        """Get LLM settings from config."""
        defaults = {
            "default_model": "gemma:2b-instruct-q4_0",
            "expansion_model": "gemma:2b-instruct-q4_0",
            "timeout_seconds": 30,
            "max_retries": 2,
        }
        settings = self._settings.get("llm_settings", {})
        return {**defaults, **settings}

    def _get_discovery_limits(self) -> dict:
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

    def _get_scraper_settings(self) -> dict:
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
        return str(random.choice(user_agents)) if user_agents else user_agents[0]

    def log(self, message: str, style: str = "") -> None:
        """Log message to provided logger or print"""
        if self.logger:
            self.logger(message, style)
        else:
            print(message)

    @contextmanager
    def managed_session(self):
        """Context manager for scraping session - creates fresh browser context per operation

        Always creates a new browser context for reliability and proper cleanup.
        Sets up event loop for Playwright sync API when running in threads.
        """
        try:
            asyncio.get_event_loop()
        except RuntimeError:
            asyncio.set_event_loop(asyncio.new_event_loop())

        scraper_settings = self._get_scraper_settings()
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=scraper_settings["headless"])
            context = browser.new_context(user_agent=self._get_random_user_agent())
            self._context = context

            try:
                yield self
            finally:
                context.close()
                browser.close()
                self._context = None

    @contextmanager
    def get_page(self) -> Generator[Page, None, None]:
        """Context manager for page - creates new page from current context"""
        if not hasattr(self, "_context") or self._context is None:
            raise RuntimeError("Scraper must be used within managed_session()")
        page = self._context.new_page()
        try:
            yield page
        finally:
            page.close()

    def _load_buckets(self) -> List[Dict[str, Any]]:
        """Load bucket configuration from DB"""
        return get_all_buckets()

    def expand_bucket(self, bucket_name: str) -> Optional[Dict[str, Any]]:
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
            return json.loads(raw)  # type: ignore[no-any-return]
        except llm.OllamaError as e:
            self.log(f"Expansion failed: {e}", "error")
            return None

    def discover_new_buckets(self) -> Optional[List[Dict[str, Any]]]:
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
            return json.loads(raw)  # type: ignore[no-any-return]
        except llm.OllamaError as e:
            self.log(f"Market discovery failed: {e}", "error")
            return None

    def generate_queries(
        self, bucket_name: Optional[str] = None, limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Generate search queries from bucket patterns, filtering out stale queries

        Args:
            bucket_name: Optional bucket name to filter queries
            limit: Optional limit override. If None, uses config or bucket default.
        """
        self.buckets = get_all_buckets()
        limits = self._get_discovery_limits()
        stale_threshold = self._settings.get("stale_query_threshold", 3)

        if limit is None:
            limit = limits["max_queries_per_run"]

        queries: List[Dict[str, Any]] = []
        buckets = [
            b for b in self.buckets if not bucket_name or b["name"] == bucket_name
        ]

        buckets.sort(key=lambda b: b.get("priority", 1), reverse=True)

        app_settings = load_json_config("app_settings.json")
        geo_focus = app_settings.get("geographic_focus") or {}

        stale_query_set = set()
        for bucket in buckets:
            bucket_id = get_bucket_id_by_name(bucket["name"])
            if bucket_id:
                stale_queries = get_stale_queries(
                    max_failures=stale_threshold, bucket_id=bucket_id
                )
                for sq in stale_queries:
                    stale_query_set.add((sq["query_pattern"], sq["city"]))

        for bucket in buckets:
            bucket_max_queries = bucket.get(
                "max_queries", limits["max_patterns_per_bucket"]
            )

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
                        cities.extend(
                            geo_focus[seg_name].get("cities", [])[:max_cities]
                        )

                if not cities:
                    self.log(
                        f"No cities found for bucket '{bucket['name']}' pattern '{pattern}'. "
                        f"Configure geographic_focus in settings.",
                        "error",
                    )
                    continue

                for city in cities:
                    if (pattern, city) in stale_query_set:
                        self.log(
                            f"  Skipping stale query: '{pattern.replace('{city}', city)}' "
                            f"({stale_threshold}+ consecutive failures)",
                            "warning",
                        )
                        continue

                    query = pattern.replace("{city}", city)
                    queries.append(
                        {
                            "query": query,
                            "bucket": bucket["name"],
                            "city": city,
                            "pattern": pattern,
                        }
                    )
                    if len(queries) >= limit:
                        return queries

        return queries[:limit]

    def scrape_google_maps(
        self, query: str, bucket: str, max_results: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Scrape Google Maps for business leads using Playwright

        Args:
            query: Search query
            bucket: Bucket name
            max_results: Optional max results override. If None, uses config.
        """
        leads: list = []
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
                        timeout=scraper_settings["search_wait_timeout_ms"],
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

    def _scrape_query(self, query_data: Dict) -> Tuple[List[Dict], Optional[Any]]:
        """Scrape a single query across all enabled sources sequentially to ensure thread-safety.

        Also tracks query performance for stale query detection.

        Returns:
            Tuple of (leads_list, query_perf_object or None)
        """
        query = query_data["query"]
        bucket = query_data["bucket"]
        city = query_data.get("city", "")
        pattern = query_data.get("pattern", query)
        query_leads: list = []

        bucket_data = next((b for b in self.buckets if b["name"] == bucket), None)
        bucket_max_results = bucket_data.get("max_results") if bucket_data else None

        bucket_id = get_bucket_id_by_name(bucket)
        query_perf = None
        if bucket_id:
            query_perf = get_or_create_query_performance(bucket_id, pattern, city)

        enabled_sources = get_all_enabled_sources(self._settings)

        sources_scrape_settings = self._settings.get("scraper_settings", {})

        for scraper in enabled_sources:
            try:
                scraper.logger = self.log
                scraper.settings = {
                    **scraper.settings,
                    **sources_scrape_settings,
                }
                max_results = scraper.get_max_results()
                if bucket_max_results and bucket_max_results < max_results:
                    max_results = bucket_max_results

                with self.get_page() as page:
                    leads = scraper.search(query, page, max_results=max_results)
                    if leads:
                        query_leads.extend(leads)
                        self.log(
                            f"  [{scraper.SOURCE_NAME}] Found {len(leads)} leads",
                            "success",
                        )
            except Exception as e:
                self.log(f"  [{scraper.SOURCE_NAME}] Error: {e}", "error")
                continue

        return query_leads, query_perf

    def run(
        self,
        bucket_name: Optional[str] = None,
        max_queries: Optional[int] = None,
    ) -> dict:
        """Execute full discovery pipeline - single-threaded with efficient resource reuse

        Args:
            bucket_name: Optional bucket name to filter queries
            max_queries: Optional max queries override. If None, uses config or bucket default.
        """
        self.buckets = self._load_buckets()
        limits = self._get_discovery_limits()

        cleanup_days = self._settings.get("stale_query_cleanup_days", 30)
        cleaned = cleanup_stale_queries(days_threshold=cleanup_days)
        if cleaned > 0:
            self.log(f"Cleaned up {cleaned} old stale queries", "info")

        if max_queries is None:
            max_queries = limits["max_queries_per_run"]

        self.log(f"\n{'=' * 60}")
        self.log("DISCOVERY: Query Generation + Lead Scraping")
        self.log(f"{'=' * 60}")

        queries = self.generate_queries(bucket_name, max_queries)
        self.log(f"Generated {len(queries)} search queries", "info")

        stale_threshold = self._settings.get("stale_query_threshold", 3)
        all_stale = get_stale_queries(max_failures=stale_threshold)
        if all_stale:
            self.log(
                f"\n{len(all_stale)} stale queries disabled (≥{stale_threshold} consecutive failures)",
                "warning",
            )

        total_leads = 0
        total_saved = 0

        with self.managed_session():
            for i, q in enumerate(queries, 1):
                self.log(f"\n[{i}/{len(queries)}] {q['query']}", "info")

                query_leads, query_perf = self._scrape_query(q)

                if query_leads:
                    saved = save_leads_batch(query_leads)
                    duplicates = len(query_leads) - saved

                    if query_perf:
                        leads_found = len(query_leads)
                        success = saved > 0
                        update_query_performance(
                            query_perf=query_perf,
                            leads_found=leads_found,
                            leads_saved=saved,
                            success=success,
                        )

                        if query_perf.consecutive_failures >= stale_threshold:
                            mark_query_as_stale(query_perf)
                            self.log(
                                f"  Query marked as STALE: {q['query']} "
                                f"({query_perf.consecutive_failures} consecutive failures)",
                                "error",
                            )

                    total_saved += saved
                    total_leads += len(query_leads)

                    if duplicates > 0:
                        self.log(
                            f"  Found {len(query_leads)} leads, saved {saved} ({duplicates} duplicates - website exists)",
                            "warning",
                        )
                    else:
                        self.log(
                            f"  Found {len(query_leads)} leads, saved {saved}",
                            "success",
                        )
                else:
                    if query_perf:
                        update_query_performance(
                            query_perf=query_perf,
                            leads_found=0,
                            leads_saved=0,
                            success=False,
                        )

                        if query_perf.consecutive_failures >= stale_threshold:
                            mark_query_as_stale(query_perf)
                            self.log(
                                f"  Query marked as STALE: {q['query']} "
                                f"({query_perf.consecutive_failures} consecutive failures)",
                                "error",
                            )

                    self.log("  No leads found", "error")

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
