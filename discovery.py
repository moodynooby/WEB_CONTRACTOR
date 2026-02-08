"""Discovery Module: Query Generation + Lead Scraping (Stage 0 + Stage A)

Performance optimizations:
- WebDriver pool for parallel scraping
- Context manager for auto-cleanup
- HTTP session reuse
- Exponential backoff decorator
- Page pooling within browsers
"""

import functools
import json
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from typing import Callable, Dict, List, Optional, TypeVar

import requests
from selenium import webdriver
from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from lead_repository import LeadRepository

T = TypeVar("T")


def exponential_backoff(max_retries: int = 3, base_delay: float = 1.0) -> Callable:
    """Decorator for exponential backoff retry logic"""
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except (requests.RequestException, WebDriverException):
                    if attempt == max_retries - 1:
                        raise
                    delay = base_delay * (2**attempt) + random.uniform(0, 1)
                    time.sleep(delay)
            return None  # type: ignore
        return wrapper
    return decorator


class WebDriverPool:
    """Thread-safe WebDriver pool for parallel scraping"""

    def __init__(
        self,
        max_drivers: int = 5,
        headless: bool = True,
    ):
        self.max_drivers = max_drivers
        self.headless = headless
        self._pool: List[webdriver.Chrome] = []
        self._in_use: set = set()
        self._lock = __import__("threading").Lock()

    def _create_driver(self) -> webdriver.Chrome:
        """Create a new Chrome driver with optimized settings"""
        chrome_options = Options()
        if self.headless:
            chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-images")
        chrome_options.add_argument("--js-flags=--max-old-space-size=512")
        chrome_options.add_argument(
            "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        chrome_options.add_experimental_option("excludeSwitches", ["enable-logging"])
        chrome_options.page_load_strategy = "eager"

        driver = webdriver.Chrome(options=chrome_options)
        driver.set_page_load_timeout(30)
        driver.implicitly_wait(5)
        return driver

    def acquire(self) -> webdriver.Chrome:
        """Acquire a driver from the pool"""
        with self._lock:
            # Reuse available driver
            for driver in list(self._pool):
                if driver not in self._in_use:
                    self._in_use.add(driver)
                    return driver

            # Create new driver if under limit
            if len(self._pool) < self.max_drivers:
                driver = self._create_driver()
                self._pool.append(driver)
                self._in_use.add(driver)
                return driver

        # Wait for available driver
        while True:
            with self._lock:
                for driver in list(self._pool):
                    if driver not in self._in_use:
                        self._in_use.add(driver)
                        return driver
            time.sleep(0.1)

    def release(self, driver: webdriver.Chrome) -> None:
        """Release a driver back to the pool"""
        with self._lock:
            self._in_use.discard(driver)

    def close_all(self) -> None:
        """Close all drivers in the pool"""
        with self._lock:
            for driver in self._pool:
                try:
                    driver.quit()
                except WebDriverException:
                    pass
            self._pool.clear()
            self._in_use.clear()

    @contextmanager
    def get_driver(self):
        """Context manager for acquiring and releasing drivers"""
        driver = self.acquire()
        try:
            yield driver
        finally:
            self.release(driver)


class Discovery:
    """Consolidated Stage 0 (Planning) + Stage A (Scraping) with performance optimizations"""

    def __init__(
        self,
        repo: Optional[LeadRepository] = None,
        logger: Optional[Callable] = None,
        max_workers: int = 5,
    ):
        self.repo = repo or LeadRepository()
        self.buckets = self._load_buckets()
        self.logger = logger
        self.ollama_url = "http://localhost:11434"
        self.max_workers = max_workers

        # WebDriver pool for parallel scraping
        self._driver_pool: Optional[WebDriverPool] = None

        # HTTP session for reuse - MUST be initialized before _test_ollama()
        self._session: Optional[requests.Session] = None

        # Test Ollama connection after _session is initialized
        self.ollama_enabled = self._test_ollama()

    def log(self, message: str, style: str = "") -> None:
        """Log message to provided logger or print"""
        if self.logger:
            self.logger(message, style)
        else:
            print(message)

    def _get_session(self) -> requests.Session:
        """Get or create reusable HTTP session"""
        if self._session is None:
            self._session = requests.Session()
            self._session.headers.update({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            })
        return self._session

    def _get_driver_pool(self) -> WebDriverPool:
        """Get or create WebDriver pool"""
        if self._driver_pool is None:
            self._driver_pool = WebDriverPool(max_drivers=self.max_workers)
        return self._driver_pool

    def _cleanup(self) -> None:
        """Cleanup all resources"""
        if self._driver_pool:
            self._driver_pool.close_all()
            self._driver_pool = None
        if self._session:
            self._session.close()
            self._session = None

    @contextmanager
    def _managed_resources(self):
        """Context manager for automatic resource cleanup"""
        try:
            yield self
        finally:
            self._cleanup()

    def _test_ollama(self) -> bool:
        """Test Ollama connection"""
        try:
            response = self._get_session().get(
                f"{self.ollama_url}/api/tags", timeout=5
            )
            return response.status_code == 200
        except requests.exceptions.RequestException:
            return False

    def _load_buckets(self) -> List[Dict]:
        """Load bucket configuration from DB"""
        return self.repo.get_all_buckets()

    def expand_bucket(self, bucket_name: str) -> Optional[Dict]:
        """Use LLM to expand bucket categories and search patterns"""
        if not self.ollama_enabled:
            return None

        bucket = next((b for b in self.buckets if b["name"] == bucket_name), None)
        if not bucket:
            return None

        self.log(f"Expanding bucket: {bucket_name} using LLM...", "info")

        prompt = f"""
        Current Lead Bucket: {bucket_name}
        Categories: {bucket.get("categories", [])}
        Search Patterns: {bucket.get("search_patterns", [])}

        This bucket is running low on leads. Suggest:
        1. 3 new related business categories
        2. 3 new search patterns using '{{city}}'
        3. 2 new target cities in India

        Return ONLY JSON:
        {{
            "new_categories": ["cat1", "cat2", "cat3"],
            "new_patterns": ["pattern1 {{city}}", "pattern2 {{city}}"],
            "new_cities": ["City1", "City2"]
        }}
        """

        try:
            response = self._get_session().post(
                f"{self.ollama_url}/api/generate",
                json={
                    "model": "qwen3:1.7b",
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",
                    "system": "You are a market research assistant. Output ONLY valid JSON.",
                },
                timeout=30,
            )

            if response.status_code == 200:
                raw = response.json().get("response", "{}")
                if not raw or raw.strip() == "":
                    self.log("Expansion LLM returned an empty response", "error")
                    return None
                try:
                    return json.loads(raw)
                except json.JSONDecodeError as e:
                    self.log(f"Failed to parse expansion JSON: {e}\nRaw: {raw}", "error")
                    return None
        except Exception as e:
            self.log(f"Expansion failed: {e}", "error")

        return None

    def discover_new_buckets(self) -> Optional[List[Dict]]:
        """Use LLM to suggest new market buckets based on current ones"""
        if not self.ollama_enabled:
            return None

        self.log("Discovering new market opportunities using LLM...", "info")

        current_buckets = [b["name"] for b in self.buckets]

        prompt = f"""
        Current Target Markets (Buckets): {current_buckets}

        Identify 2 new industries or business niches that would benefit from web development or SEO services.
        For each, provide:
        - A bucket name
        - 3 initial business categories
        - 2 search patterns using '{{city}}'

        Return ONLY JSON list of objects:
        [
            {{
                "name": "Market Name",
                "categories": ["cat1", "cat2"],
                "search_patterns": ["pattern1 {{city}}"]
            }}
        ]
        """

        try:
            response = self._get_session().post(
                f"{self.ollama_url}/api/generate",
                json={
                    "model": "qwen3:1.7b",
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",
                    "system": "You are a business strategist. Output ONLY valid JSON.",
                },
                timeout=30,
            )

            if response.status_code == 200:
                raw = response.json().get("response", "[]")
                if not raw or raw.strip() == "":
                    self.log("Market discovery LLM returned an empty response", "error")
                    return None
                try:
                    return json.loads(raw)
                except json.JSONDecodeError as e:
                    self.log(f"Failed to parse market discovery JSON: {e}\nRaw: {raw}", "error")
                    return None
        except Exception as e:
            self.log(f"Market discovery failed: {e}", "error")

        return None

    def generate_queries(
        self, bucket_name: Optional[str] = None, limit: int = 20
    ) -> List[Dict]:
        """Generate search queries from bucket patterns"""
        self.buckets = self._load_buckets()
        queries = []
        buckets = [b for b in self.buckets if not bucket_name or b["name"] == bucket_name]

        # Load geographic focus from DB
        geo_focus = self.repo.get_config("geographic_focus") or {}

        for bucket in buckets:
            search_patterns = bucket.get("search_patterns", [])
            # Handle if search_patterns is string (should be parsed by repo, but safety check)
            if isinstance(search_patterns, str):
                try:
                    search_patterns = json.loads(search_patterns)
                except json.JSONDecodeError as e:
                    self.log(f"Invalid JSON in search_patterns: {e}", "error")
                    search_patterns = []

            for pattern in search_patterns[:3]:
                # Get cities from geographic segments
                cities = []
                segments = bucket.get("geographic_segments", [])
                if isinstance(segments, str):
                    try:
                        segments = json.loads(segments)
                    except json.JSONDecodeError as e:
                        self.log(f"Invalid JSON in geographic_segments: {e}", "error")
                        segments = []

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
                    queries.append({"query": query, "bucket": bucket["name"], "city": city})
                    if len(queries) >= limit:
                        return queries

        return queries[:limit]

    @exponential_backoff(max_retries=3, base_delay=1.0)
    def _scrape_with_driver(
        self, url: str, css_selector: str, driver: webdriver.Chrome
    ) -> bool:
        """Scrape a URL with exponential backoff retry"""
        driver.get(url)
        time.sleep(2)
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, css_selector))
        )
        return True

    def scrape_google_maps(
        self, query: str, bucket: str, max_results: int = 5
    ) -> List[Dict]:
        """Scrape Google Maps for business leads using pooled driver"""
        leads: List[Dict] = []
        pool = self._get_driver_pool()

        with pool.get_driver() as driver:
            try:
                search_url = f"https://www.google.com/maps/search/{query.replace(' ', '+')}"
                driver.get(search_url)
                time.sleep(3)

                # Wait for results
                try:
                    WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located(
                            (By.CSS_SELECTOR, "a[href*='/maps/place/']")
                        )
                    )
                except TimeoutException:
                    self.log(
                        f"Google Maps search results not loaded for query '{query}'", "error"
                    )
                    return leads

                # Get business listings
                business_elements = driver.find_elements(
                    By.CSS_SELECTOR, "a[href*='/maps/place/']"
                )[:max_results]

                for element in business_elements:
                    try:
                        element.click()
                        time.sleep(2)

                        # Extract business name
                        try:
                            name = driver.find_element(By.CSS_SELECTOR, "h1.DUwDvf").text
                        except NoSuchElementException:
                            name = "Unknown Business"
                        except Exception as e:
                            self.log(f"Unexpected error finding business name: {e}", "error")
                            name = "Unknown Business"

                        # Extract website
                        website = None
                        try:
                            website_element = driver.find_element(
                                By.CSS_SELECTOR, "a[data-item-id*='authority']"
                            )
                            website = website_element.get_attribute("href")
                        except NoSuchElementException:
                            pass
                        except Exception as e:
                            self.log(f"Error extracting website from Google Maps: {e}", "error")

                        # Extract phone
                        phone = None
                        try:
                            phone_element = driver.find_element(
                                By.CSS_SELECTOR, "button[data-item-id*='phone']"
                            )
                            phone = phone_element.get_attribute("aria-label")
                        except NoSuchElementException:
                            pass
                        except Exception as e:
                            self.log(f"Error extracting phone from Google Maps: {e}", "error")

                        if name:
                            leads.append(
                                {
                                    "business_name": name,
                                    "website": website,
                                    "phone": phone,
                                    "source": "google_maps",
                                    "bucket": bucket,
                                    "category": query.split()[0],
                                    "location": query.split()[-1] if " " in query else "Unknown",
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
        """Scrape JustDial for Indian business leads using pooled driver"""
        leads: List[Dict] = []
        pool = self._get_driver_pool()

        with pool.get_driver() as driver:
            try:
                # Format query for JustDial URL
                query_parts = query.split()
                city = query_parts[-1] if len(query_parts) > 1 else "Mumbai"
                search_term = " ".join(query_parts[:-1]) if len(query_parts) > 1 else query
                search_url = f"https://www.justdial.com/{city}/{search_term.replace(' ', '-')}"

                driver.get(search_url)
                time.sleep(3)

                # Wait for results
                try:
                    WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located(
                            (By.CSS_SELECTOR, ".jsx-1e1a185d7f5319c2")
                        )
                    )
                except TimeoutException:
                    self.log(
                        f"JustDial search results not loaded for query '{query}'", "error"
                    )
                    return leads

                # Get business listings
                business_elements = driver.find_elements(
                    By.CSS_SELECTOR, ".jsx-1e1a185d7f5319c2"
                )[:max_results]

                for element in business_elements:
                    try:
                        # Extract business name
                        try:
                            name_elem = element.find_element(
                                By.CSS_SELECTOR, ".jsx-2c8ae8c8b6b8b1b0"
                            )
                            name = name_elem.text.strip() if name_elem else "Unknown Business"
                        except NoSuchElementException:
                            name = "Unknown Business"

                        # Extract phone
                        phone = None
                        try:
                            phone_elem = element.find_element(
                                By.CSS_SELECTOR, ".jsx-3c8ae8c8b6b8b1b0"
                            )
                            phone = phone_elem.text.strip() if phone_elem else None
                        except NoSuchElementException:
                            pass
                        except Exception as e:
                            self.log(f"Error extracting phone from JustDial: {e}", "error")

                        # Extract website (often requires clicking through)
                        website = None
                        try:
                            website_elem = element.find_element(
                                By.CSS_SELECTOR, "a[href*='http']"
                            )
                            website = (
                                website_elem.get_attribute("href") if website_elem else None
                            )
                        except NoSuchElementException:
                            pass
                        except Exception as e:
                            self.log(f"Error extracting website from JustDial: {e}", "error")

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
        """Scrape IndiaMART for B2B business leads using pooled driver"""
        leads: List[Dict] = []
        pool = self._get_driver_pool()

        with pool.get_driver() as driver:
            try:
                search_url = f"https://dir.indiamart.com/search.mp?search={query.replace(' ', '+')}"
                driver.get(search_url)
                time.sleep(3)

                # Wait for results
                try:
                    WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, ".pbox"))
                    )
                except TimeoutException:
                    self.log(
                        f"IndiaMART search results not loaded for query '{query}'", "error"
                    )
                    return leads

                # Get business listings
                business_elements = driver.find_elements(By.CSS_SELECTOR, ".pbox")[
                    :max_results
                ]

                for element in business_elements:
                    try:
                        # Extract business name
                        try:
                            name_elem = element.find_element(By.CSS_SELECTOR, ".lst_clg a")
                            name = name_elem.text.strip() if name_elem else "Unknown Business"
                        except NoSuchElementException:
                            name = "Unknown Business"

                        # Extract website
                        website = None
                        try:
                            website_elem = element.find_element(
                                By.CSS_SELECTOR, ".lst_clg a"
                            )
                            website = (
                                website_elem.get_attribute("href") if website_elem else None
                            )
                        except NoSuchElementException:
                            pass
                        except Exception as e:
                            self.log(f"Error extracting website from IndiaMART: {e}", "error")

                        # Extract phone
                        phone = None
                        try:
                            phone_elem = element.find_element(By.CSS_SELECTOR, ".pnum")
                            phone = phone_elem.text.strip() if phone_elem else None
                        except NoSuchElementException:
                            pass
                        except Exception as e:
                            self.log(f"Error extracting phone from IndiaMART: {e}", "error")

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
        """Scrape Yelp for business leads using pooled driver"""
        leads: List[Dict] = []
        pool = self._get_driver_pool()

        with pool.get_driver() as driver:
            try:
                search_url = f"https://www.yelp.com/search?find_desc={query.replace(' ', '+')}"
                driver.get(search_url)
                time.sleep(3)

                # Wait for results
                try:
                    WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located(
                            (By.CSS_SELECTOR, ".container__09f24__mpRFF")
                        )
                    )
                except TimeoutException:
                    self.log(f"Yelp search results not loaded for query '{query}'", "error")
                    return leads

                # Get business listings
                business_elements = driver.find_elements(
                    By.CSS_SELECTOR, ".container__09f24__mpRFF"
                )[:max_results]

                for element in business_elements:
                    try:
                        # Extract business name
                        try:
                            name_elem = element.find_element(
                                By.CSS_SELECTOR, "a[href*='/biz/']"
                            )
                            name = name_elem.text.strip() if name_elem else "Unknown Business"
                        except NoSuchElementException:
                            name = "Unknown Business"

                        # Extract website
                        website = None
                        try:
                            website_elem = element.find_element(
                                By.CSS_SELECTOR, "a[href*='biz/']"
                            )
                            website = (
                                website_elem.get_attribute("href") if website_elem else None
                            )
                        except NoSuchElementException:
                            pass
                        except Exception as e:
                            self.log(f"Error extracting website from Yelp: {e}", "error")

                        # Extract phone
                        phone = None
                        try:
                            phone_elem = element.find_element(
                                By.CSS_SELECTOR, ".phone__09f24__pARZf"
                            )
                            phone = phone_elem.text.strip() if phone_elem else None
                        except NoSuchElementException:
                            pass
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

        # Source 1: Google Maps
        query_leads.extend(self.scrape_google_maps(query, bucket, max_results=2))

        # Source 2: JustDial
        if len(query_leads) < 3:
            query_leads.extend(
                self.scrape_justdial(query, bucket, 3 - len(query_leads))
            )

        # Source 3: IndiaMART
        if len(query_leads) < 3:
            query_leads.extend(
                self.scrape_indiamart(query, bucket, 3 - len(query_leads))
            )

        # Source 4: Yelp
        if len(query_leads) < 3:
            query_leads.extend(self.scrape_yelp(query, bucket, 3 - len(query_leads)))

        return query_leads

    def run(
        self,
        bucket_name: Optional[str] = None,
        max_queries: int = 5,
        parallel: bool = True,
    ) -> Dict:
        """Execute full discovery pipeline with driver pooling and batch saving"""
        self.buckets = self._load_buckets()
        self.log(f"\n{'=' * 60}")
        self.log("DISCOVERY: Query Generation + Lead Scraping")
        self.log(f"{'=' * 60}")

        # Stage 0: Generate queries
        queries = self.generate_queries(bucket_name, max_queries)
        self.log(f"Generated {len(queries)} search queries", "info")

        # Stage A: Scrape leads
        total_leads = 0
        total_saved = 0

        with self._managed_resources():
            if parallel and len(queries) > 1:
                # Parallel scraping
                with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                    futures = {executor.submit(self._scrape_query, q): q for q in queries}

                    for i, future in enumerate(as_completed(futures), 1):
                        query_data = futures[future]
                        self.log(f"\n[{i}/{len(queries)}] {query_data['query']}", "info")

                        try:
                            query_leads = future.result(timeout=120)

                            # Batch Save leads to database
                            if query_leads:
                                saved = self.repo.save_leads_batch(query_leads)
                                total_saved += saved
                                total_leads += len(query_leads)
                                self.log(
                                    f"  Found {len(query_leads)} leads, saved {saved}",
                                    "success",
                                )
                        except Exception as e:
                            self.log(f"  Error processing query: {e}", "error")
            else:
                # Sequential scraping
                for i, q in enumerate(queries, 1):
                    self.log(f"\n[{i}/{len(queries)}] {q['query']}", "info")

                    query_leads = self._scrape_query(q)

                    # Batch Save leads to database
                    if query_leads:
                        saved = self.repo.save_leads_batch(query_leads)
                        total_saved += saved
                        total_leads += len(query_leads)
                        self.log(
                            f"  Found {len(query_leads)} leads, saved {saved}", "success"
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
