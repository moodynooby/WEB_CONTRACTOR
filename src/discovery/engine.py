"""Discovery Module: Query Generation + Lead Scraping (Stage 0 + Stage A)

This module handles lead discovery by generating search queries and scraping
results from multiple sources using Playwright browser automation.

⚠️  PLAYWRIGHT THREADING LIMITATIONS ⚠️
========================================
Playwright's sync API is NOT thread-safe due to its internal use of greenlets
for async-to-sync conversion. Key constraints:

1. **No ThreadPoolExecutor**: Cannot parallelize scraping across sources.
   Each Playwright operation must run sequentially on the same thread.
   Attempting parallel execution raises:
   - "Cannot switch to a different thread" (greenlet.error)
   - "It looks like you are using Playwright Sync API inside the asyncio loop"

2. **Thread-local instances**: Playwright instances must be thread-local via
   threading.local(). Sharing a global instance across threads fails because
   greenlets maintain thread-specific execution contexts.

3. **Sequential execution**: Sources scrape one-by-one, not in parallel.
   Each source gets its own isolated browser context for safety.

4. **Context managers required**: Always use managed_session() to ensure
   proper browser/context/page lifecycle management and cleanup.

If you need to parallelize, consider:
- Playwright's async_api (requires async/await throughout codebase)
- Multiprocessing (separate processes, not threads)
- Running multiple independent script instances

References:
- https://playwright.dev/python/docs/library#thread-safety
- https://github.com/microsoft/playwright-python/issues/1033
"""

import json
import threading
from contextlib import contextmanager
from typing import Any, Callable, Generator

from playwright.sync_api import Playwright, Page, sync_playwright

from infra.settings import DEFAULT_USER_AGENT, get_section
from infra.logging import get_logger
from database.bucket_repo import get_all_buckets, get_bucket_id_by_name
from database.lead_repo import save_leads_batch
from database.query_perf_repo import (
    get_or_create_query_performance,
    update_query_performance,
    mark_query_as_stale,
    get_stale_queries,
    cleanup_stale_queries,
)
from discovery.sources import get_all_enabled_sources


_local = threading.local()


def _get_playwright() -> Playwright:
    """Get or create thread-local Playwright instance.

    Playwright's sync API uses greenlets which are thread-local,
    so each thread needs its own instance to avoid 'Cannot switch
    to a different thread' errors.

    Returns:
        Playwright instance for the current thread
    """
    if not hasattr(_local, "playwright"):
        _local.playwright = sync_playwright().start()
    return _local.playwright


def _build_discovery_settings() -> dict[str, Any]:
    """Merge relevant sections into one flat dict."""
    cfg = get_section("scraper") or {}
    limits = get_section("discovery_limits") or {}
    sources = get_section("discovery_sources") or {}
    anti = get_section("anti_detection") or {}
    parallel = get_section("parallel") or {}
    scoring = get_section("query_scoring") or {}
    perf = get_section("query_performance") or {}
    all_cfg = {**cfg, **limits, **sources, **anti, **parallel, **scoring, **perf}
    from infra.settings import STALE_QUERY_THRESHOLD, STALE_QUERY_CLEANUP_DAYS

    all_cfg["stale_query_threshold"] = STALE_QUERY_THRESHOLD
    all_cfg["stale_query_cleanup_days"] = STALE_QUERY_CLEANUP_DAYS
    return all_cfg


class PlaywrightScraper:
    """Consolidated Stage 0 (Planning) + Stage A (Scraping).

    Handles query generation and lead scraping using Playwright browser
    automation. All operations run sequentially due to Playwright's sync
    API thread-safety limitations.

    Usage:
        scraper = PlaywrightScraper()
        with scraper.managed_session():
            # Queries are generated from bucket patterns
            queries = scraper.create_search_queries()
            # Each query is scraped across all enabled sources sequentially
            results = scraper.run()

    Note:
        Do NOT attempt to parallelize scraping operations. Each source
        must run sequentially within the same thread to avoid greenlet
        thread-switching errors.
    """

    def __init__(self):
        self.logger = get_logger(__name__)
        self._settings = _build_discovery_settings()
        self._buckets_cache: list[dict[str, Any]] | None = None

    @property
    def buckets(self) -> list[dict[str, Any]]:
        """Lazy load buckets with caching."""
        if self._buckets_cache is None:
            self._buckets_cache = get_all_buckets()
        return self._buckets_cache

    @contextmanager
    def managed_session(self):
        """Context manager for Playwright browser session.

        Creates a thread-local Playwright instance and launches a browser
        with a fresh context. This ensures proper resource lifecycle management.

        ⚠️  IMPORTANT: This MUST be used as a context manager:
            with scraper.managed_session():
                # scraping operations here

        The session provides:
        - Thread-local Playwright instance (avoiding greenlet conflicts)
        - Browser instance with configured user agent
        - Browser context for isolation
        - Automatic cleanup of all resources on exit

        Raises:
            playwright._impl._errors.Error: If called from within an
                asyncio event loop without proper isolation
        """
        pw = _get_playwright()
        browser = pw.chromium.launch(
            headless=self._settings.get("scraper_settings", {}).get("headless", True)
        )
        context = browser.new_context(user_agent=DEFAULT_USER_AGENT)
        self._context = context
        self._browser = browser

        try:
            yield self
        finally:
            context.close()
            browser.close()
            self._context = None
            self._browser = None

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

    def create_search_queries(
        self, bucket_name: str | None = None, limit: int | None = None
    ) -> list[dict[str, Any]]:
        """Generate search queries from bucket patterns, filtering out stale queries

        Args:
            bucket_name: Optional bucket name to filter queries
            limit: Optional limit override. If None, uses config or bucket default.
        """
        limit = limit or self._settings.get("max_queries_per_run", 500)
        stale_threshold = self._settings.get("stale_query_threshold", 3)

        queries: list[dict[str, Any]] = []
        buckets = [
            b for b in self.buckets if not bucket_name or b["name"] == bucket_name
        ]

        buckets.sort(key=lambda b: b.get("priority", 1), reverse=True)

        geo_focus = get_section("geographic_focus")

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
            bucket_max_queries = int(
                bucket.get(
                    "max_queries", self._settings.get("max_patterns_per_bucket", 500)
                )
            )

            search_patterns = bucket.get("search_patterns", [])
            if isinstance(search_patterns, str):
                try:
                    search_patterns = json.loads(search_patterns)
                except json.JSONDecodeError as e:
                    self.logger.error(f"Invalid JSON in search_patterns: {e}")
                    search_patterns = []

            for pattern in search_patterns[:bucket_max_queries]:
                cities = []
                segments = bucket.get("geographic_segments", [])
                if isinstance(segments, str):
                    try:
                        segments = json.loads(segments)
                    except json.JSONDecodeError as e:
                        self.logger.error(f"Invalid JSON in geographic_segments: {e}")
                        segments = []

                if not segments:
                    segments = ["tier_1_metros"]

                for seg_name in segments:
                    if seg_name in geo_focus:
                        max_cities = int(
                            self._settings.get("max_cities_per_segment", 50)
                        )
                        cities.extend(
                            geo_focus[seg_name].get("cities", [])[:max_cities]
                        )
                    else:
                        cities.append(seg_name)

                if not cities:
                    self.logger.error(
                        f"No cities found for bucket '{bucket['name']}' pattern '{pattern}'. "
                        f"Configure geographic_focus in settings.",
                    )
                    continue

                for city in cities:
                    if (pattern, city) in stale_query_set:
                        self.logger.warning(
                            f"  Skipping stale query: '{pattern.replace('{city}', city)}' "
                            f"({stale_threshold}+ consecutive failures)",
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

    def _scrape_sources(
        self,
        query_data: dict,
        bucket_max_results: int | None,
        query_perf: Any | None,
    ) -> tuple[list[dict], Any | None]:
        """Scrape a query across all enabled sources sequentially.

        ⚠️  THREAD-SAFETY: Playwright sync API is NOT thread-safe.
        Sources MUST run sequentially, not in parallel, because:
        - Playwright uses greenlets for async-to-sync conversion
        - Greenlets are thread-local and cannot switch threads
        - Parallel execution causes: "Cannot switch to a different thread"

        Each source gets its own isolated browser context for safety.
        A single browser instance is shared across all sources for efficiency.

        Args:
            query_data: Query information (query, bucket, city, pattern)
            bucket_max_results: Maximum results per query (from bucket config)
            query_perf: Query performance tracking object

        Returns:
            Tuple of (list of normalized leads, query performance object)
        """
        query = query_data["query"]
        bucket = query_data["bucket"]
        query_leads: list = []

        region = "India"
        enabled_sources = get_all_enabled_sources(self._settings, region=region)

        if not enabled_sources:
            self.logger.warning(f"  No enabled sources found for region: {region}")
            return query_leads, query_perf

        sources_scrape_settings = self._settings.get("scraper_settings", {})

        self.logger.info(
            f"  Scraping {len(enabled_sources)} sources ({region})...",
        )

        pw = _get_playwright()
        browser = pw.chromium.launch(
            headless=sources_scrape_settings.get("headless", True)
        )

        try:
            for scraper in enabled_sources:
                context = None
                page = None
                try:
                    context = browser.new_context(
                        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                    )
                    page = context.new_page()

                    max_results = int(scraper.get_max_results())
                    if bucket_max_results and bucket_max_results < max_results:
                        max_results = int(bucket_max_results)

                    leads = scraper.search(query, page, max_results=max_results)

                    if leads:
                        normalized = [
                            scraper.normalize_lead(lead, bucket=bucket, query=query)
                            for lead in leads
                        ]
                        query_leads.extend(normalized)
                        self.logger.info(
                            f"  [{scraper.SOURCE_NAME}] Found {len(leads)} leads",
                        )

                except Exception as e:
                    self.logger.error(f"  [{scraper.SOURCE_NAME}] Failed: {e}")
                finally:
                    if page:
                        page.close()
                    if context:
                        context.close()
        finally:
            browser.close()

        self.logger.info(f"  Total: {len(query_leads)} leads from all sources")
        return query_leads, query_perf

    def run(
        self,
        bucket_name: str | None = None,
        max_queries: int | None = None,
        progress_callback: Callable[[int, int, str], None] | None = None,
    ) -> dict:
        """Execute full discovery pipeline - sequential query processing.

        This method runs the complete discovery workflow:
        1. Load buckets and clean up stale queries
        2. Generate search queries from bucket patterns
        3. For each query, scrape all enabled sources sequentially
        4. Save discovered leads to database
        5. Update query performance metrics

        ⚠️  THREADING: This runs in a single thread due to Playwright's
        sync API limitations. Do NOT attempt to parallelize source scraping.

        The pipeline MUST be called within a managed_session() context.

        Args:
            bucket_name: Optional bucket name to filter queries
            max_queries: Optional max queries override. If None, uses config or bucket default.
            progress_callback: Optional callback(current, total, message)

        Returns:
            Dict with keys: queries_executed, leads_found, leads_saved
        """
        max_queries = max_queries or self._settings.get("max_queries_per_run", 500)

        cleanup_days = self._settings.get("stale_query_cleanup_days", 30)
        cleaned = cleanup_stale_queries(days_threshold=cleanup_days)
        if cleaned > 0:
            self.logger.info(f"Cleaned up {cleaned} old stale queries")

        self.logger.info("DISCOVERY: Query Generation + Lead Scraping")

        queries = self.create_search_queries(bucket_name, max_queries)
        self.logger.info(f"Generated {len(queries)} search queries")

        stale_threshold = self._settings.get("stale_query_threshold", 3)
        all_stale = get_stale_queries(max_failures=stale_threshold)
        if all_stale:
            self.logger.warning(
                f"\n{len(all_stale)} stale queries disabled (≥{stale_threshold} consecutive failures)",
            )

        total_leads = 0
        total_saved = 0

        with self.managed_session():
            for i, q in enumerate(queries, 1):
                msg = f"Processing query: {q['query']}"
                self.logger.info(f"\n[{i}/{len(queries)}] {q['query']}")

                if progress_callback:
                    progress_callback(i, len(queries), msg)

                bucket_data = next(
                    (b for b in self.buckets if b["name"] == q["bucket"]), None
                )
                max_res = bucket_data.get("max_results") if bucket_data else None
                bucket_max_results = int(max_res) if max_res is not None else None

                bucket_id = get_bucket_id_by_name(q["bucket"])
                query_perf = None
                if bucket_id:
                    query_perf = get_or_create_query_performance(
                        bucket_id, q["pattern"], q["city"]
                    )

                query_leads, query_perf = self._scrape_sources(
                    q, bucket_max_results, query_perf
                )

                if query_leads:
                    saved = save_leads_batch(query_leads)
                    duplicates = len(query_leads) - saved

                    if query_perf:
                        leads_found = len(query_leads)
                        success = saved > 0
                        update_query_performance(
                            qp_id=query_perf["id"],
                            leads_found=leads_found,
                            leads_saved=saved,
                            success=success,
                        )

                        if query_perf.get("consecutive_failures", 0) >= stale_threshold:
                            mark_query_as_stale(query_perf["id"])
                            self.logger.error(
                                f"  Query marked as STALE: {q['query']} "
                                f"({query_perf.get('consecutive_failures', 0)} consecutive failures)",
                            )

                    total_saved += saved
                    total_leads += len(query_leads)

                    if duplicates > 0:
                        self.logger.warning(
                            f"  Found {len(query_leads)} leads, saved {saved} ({duplicates} duplicates - website exists)",
                        )
                    else:
                        self.logger.info(
                            f"  Found {len(query_leads)} leads, saved {saved}",
                        )
                else:
                    if query_perf:
                        update_query_performance(
                            qp_id=query_perf["id"],
                            leads_found=0,
                            leads_saved=0,
                            success=False,
                        )

                        if query_perf.get("consecutive_failures", 0) >= stale_threshold:
                            mark_query_as_stale(query_perf["id"])
                            self.logger.error(
                                f"  Query marked as STALE: {q['query']} "
                                f"({query_perf.get('consecutive_failures', 0)} consecutive failures)",
                            )

                    self.logger.error("  No leads found")

        self.logger.info(f"\n{'=' * 60}")
        self.logger.info(
            f"Discovery Complete: {total_leads} found, {total_saved} saved"
        )
        self.logger.info(f"{'=' * 60}\n")

        return {
            "queries_executed": len(queries),
            "leads_found": total_leads,
            "leads_saved": total_saved,
        }


