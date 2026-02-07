"""Discovery Module: Query Generation + Lead Scraping (Stage 0 + Stage A)"""

import json
import time
import requests
from typing import List, Dict, Optional
from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from lead_repository import LeadRepository


class Discovery:
    """Consolidated Stage 0 (Planning) + Stage A (Scraping)"""

    def __init__(self, repo: Optional[LeadRepository] = None, logger=None):
        self.repo = repo or LeadRepository()
        self.buckets = self._load_buckets()
        self.logger = logger
        self.ollama_url = "http://localhost:11434"
        self.ollama_enabled = self._test_ollama()
        self._driver: Optional[webdriver.Chrome] = None

    def _get_driver(self) -> Optional[webdriver.Chrome]:
        """Lazy initialization of headless Chrome driver"""
        if self._driver is None:
            try:
                chrome_options = Options()
                chrome_options.add_argument("--headless")
                chrome_options.add_argument("--no-sandbox")
                chrome_options.add_argument("--disable-dev-shm-usage")
                chrome_options.add_argument("--disable-gpu")
                chrome_options.add_argument(
                    "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                )
                self._driver = webdriver.Chrome(options=chrome_options)
                self._driver.set_page_load_timeout(30)
            except Exception as e:
                self.log(f"Failed to initialize Chrome driver: {e}", "error")
        return self._driver

    def _quit_driver(self):
        """Properly shut down the driver"""
        if self._driver:
            try:
                self._driver.quit()
            except WebDriverException:
                pass
            self._driver = None

    def _test_ollama(self) -> bool:
        """Test Ollama connection"""
        try:
            response = requests.get(f"{self.ollama_url}/api/tags", timeout=5)
            return response.status_code == 200
        except requests.exceptions.RequestException:
            return False

    def log(self, message: str, style: str = ""):
        """Log message to provided logger or print"""
        if self.logger:
            self.logger(message, style)
        else:
            print(message)

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
            response = requests.post(
                f"{self.ollama_url}/api/generate",
                json={
                    "model": "qwen3:8b",
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",
                    "system": "You are a market research assistant. Output ONLY valid JSON.",
                },
                timeout=30,
            )

            if response.status_code == 200:
                raw = response.json().get("response", "{}")
                return json.loads(raw)
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
            response = requests.post(
                f"{self.ollama_url}/api/generate",
                json={
                    "model": "qwen3:8b",
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",
                    "system": "You are a business strategist. Output ONLY valid JSON.",
                },
                timeout=30,
            )

            if response.status_code == 200:
                raw = response.json().get("response", "[]")
                return json.loads(raw)
        except Exception as e:
            self.log(f"Market discovery failed: {e}", "error")

        return None

    def generate_queries(self, bucket_name: str = None, limit: int = 20) -> List[Dict]:
        """Generate search queries from bucket patterns"""
        self.buckets = self._load_buckets()
        queries = []
        buckets = [
            b for b in self.buckets if not bucket_name or b["name"] == bucket_name
        ]

        # Load geographic focus from DB
        geo_focus = self.repo.get_config("geographic_focus") or {}

        for bucket in buckets:
            search_patterns = bucket.get("search_patterns", [])
            # Handle if search_patterns is string (should be parsed by repo, but safety check)
            if isinstance(search_patterns, str):
                try:
                    search_patterns = json.loads(search_patterns)
                except:
                    search_patterns = []

            for pattern in search_patterns[:3]:
                # Get cities from geographic segments
                cities = []
                segments = bucket.get("geographic_segments", [])
                if isinstance(segments, str):
                    try:
                        segments = json.loads(segments)
                    except:
                        segments = []

                for seg_name in segments:
                    if seg_name in geo_focus:
                        cities.extend(geo_focus[seg_name].get("cities", [])[:2])

                if not cities:
                    cities = ["Mumbai", "Delhi", "Bangalore"]

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
        """Scrape Google Maps for business leads using pooled driver"""
        leads = []
        driver = self._get_driver()
        if not driver:
            return leads

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
            except:
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
                    except:
                        name = "Unknown Business"

                    # Extract website
                    website = None
                    try:
                        website_element = driver.find_element(
                            By.CSS_SELECTOR, "a[data-item-id*='authority']"
                        )
                        website = website_element.get_attribute("href")
                    except:
                        pass

                    # Extract phone
                    phone = None
                    try:
                        phone_element = driver.find_element(
                            By.CSS_SELECTOR, "button[data-item-id*='phone']"
                        )
                        phone = phone_element.get_attribute("aria-label")
                    except:
                        pass

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
        """Scrape JustDial for Indian business leads using pooled driver"""
        leads = []
        driver = self._get_driver()
        if not driver:
            return leads

        try:
            # Format query for JustDial URL
            query_parts = query.split()
            city = query_parts[-1] if len(query_parts) > 1 else "Mumbai"
            search_term = " ".join(query_parts[:-1]) if len(query_parts) > 1 else query
            search_url = (
                f"https://www.justdial.com/{city}/{search_term.replace(' ', '-')}"
            )

            driver.get(search_url)
            time.sleep(3)

            # Wait for results
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, ".jsx-1e1a185d7f5319c2")
                    )
                )
            except:
                return leads

            # Get business listings
            business_elements = driver.find_elements(
                By.CSS_SELECTOR, ".jsx-1e1a185d7f5319c2"
            )[:max_results]

            for element in business_elements:
                try:
                    # Extract business name
                    name_elem = element.find_element(
                        By.CSS_SELECTOR, ".jsx-2c8ae8c8b6b8b1b0"
                    )
                    name = name_elem.text.strip() if name_elem else "Unknown Business"

                    # Extract phone
                    phone = None
                    try:
                        phone_elem = element.find_element(
                            By.CSS_SELECTOR, ".jsx-3c8ae8c8b6b8b1b0"
                        )
                        phone = phone_elem.text.strip() if phone_elem else None
                    except:
                        pass

                    # Extract website (often requires clicking through)
                    website = None
                    try:
                        website_elem = element.find_element(
                            By.CSS_SELECTOR, "a[href*='http']"
                        )
                        website = (
                            website_elem.get_attribute("href") if website_elem else None
                        )
                    except:
                        pass

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

    def scrape_yellowpages(
        self, query: str, bucket: str, max_results: int = 5
    ) -> List[Dict]:
        """Scrape Yellow Pages for business leads using pooled driver"""
        leads = []
        driver = self._get_driver()
        if not driver:
            return leads

        try:
            search_url = f"https://www.yellowpages.com/search?search_terms={query.replace(' ', '+')}"
            driver.get(search_url)
            time.sleep(3)

            # Wait for results
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, ".result"))
                )
            except:
                return leads

            # Get business listings
            business_elements = driver.find_elements(By.CSS_SELECTOR, ".result")[
                :max_results
            ]

            for element in business_elements:
                try:
                    # Extract business name
                    name_elem = element.find_element(By.CSS_SELECTOR, "a.business-name")
                    name = name_elem.text.strip() if name_elem else "Unknown Business"

                    # Extract website
                    website = None
                    try:
                        website_elem = element.find_element(
                            By.CSS_SELECTOR, "a.website-link"
                        )
                        website = (
                            website_elem.get_attribute("href") if website_elem else None
                        )
                    except:
                        pass

                    # Extract phone
                    phone = None
                    try:
                        phone_elem = element.find_element(By.CSS_SELECTOR, ".phone")
                        phone = phone_elem.text.strip() if phone_elem else None
                    except:
                        pass

                    if name:
                        leads.append(
                            {
                                "business_name": name,
                                "website": website,
                                "phone": phone,
                                "source": "yellowpages",
                                "bucket": bucket,
                                "category": query.split()[0],
                                "location": "USA",
                            }
                        )

                except Exception:
                    continue

        except Exception as e:
            self.log(f"Error scraping Yellow Pages: {e}", "error")

        return leads

    def scrape_indiamart(
        self, query: str, bucket: str, max_results: int = 5
    ) -> List[Dict]:
        """Scrape IndiaMART for B2B business leads using pooled driver"""
        leads = []
        driver = self._get_driver()
        if not driver:
            return leads

        try:
            search_url = (
                f"https://dir.indiamart.com/search.mp?search={query.replace(' ', '+')}"
            )
            driver.get(search_url)
            time.sleep(3)

            # Wait for results
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, ".pbox"))
                )
            except:
                return leads

            # Get business listings
            business_elements = driver.find_elements(By.CSS_SELECTOR, ".pbox")[
                :max_results
            ]

            for element in business_elements:
                try:
                    # Extract business name
                    name_elem = element.find_element(By.CSS_SELECTOR, ".lst_clg a")
                    name = name_elem.text.strip() if name_elem else "Unknown Business"

                    # Extract website
                    website = None
                    try:
                        website_elem = element.find_element(
                            By.CSS_SELECTOR, ".lst_clg a"
                        )
                        website = (
                            website_elem.get_attribute("href") if website_elem else None
                        )
                    except:
                        pass

                    # Extract phone
                    phone = None
                    try:
                        phone_elem = element.find_element(By.CSS_SELECTOR, ".pnum")
                        phone = phone_elem.text.strip() if phone_elem else None
                    except:
                        pass

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

                except Exception:
                    continue

        except Exception as e:
            self.log(f"Error scraping IndiaMART: {e}", "error")

        return leads

    def scrape_yelp(self, query: str, bucket: str, max_results: int = 5) -> List[Dict]:
        """Scrape Yelp for business leads using pooled driver"""
        leads = []
        driver = self._get_driver()
        if not driver:
            return leads

        try:
            search_url = (
                f"https://www.yelp.com/search?find_desc={query.replace(' ', '+')}"
            )
            driver.get(search_url)
            time.sleep(3)

            # Wait for results
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, ".container__09f24__mpRFF")
                    )
                )
            except:
                return leads

            # Get business listings
            business_elements = driver.find_elements(
                By.CSS_SELECTOR, ".container__09f24__mpRFF"
            )[:max_results]

            for element in business_elements:
                try:
                    # Extract business name
                    name_elem = element.find_element(
                        By.CSS_SELECTOR, "a[href*='/biz/']"
                    )
                    name = name_elem.text.strip() if name_elem else "Unknown Business"

                    # Extract website
                    website = None
                    try:
                        website_elem = element.find_element(
                            By.CSS_SELECTOR, "a[href*='biz/']"
                        )
                        website = (
                            website_elem.get_attribute("href") if website_elem else None
                        )
                    except:
                        pass

                    # Extract phone
                    phone = None
                    try:
                        phone_elem = element.find_element(
                            By.CSS_SELECTOR, ".phone__09f24__pARZf"
                        )
                        phone = phone_elem.text.strip() if phone_elem else None
                    except:
                        pass

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

                except Exception:
                    continue

        except Exception as e:
            self.log(f"Error scraping Yelp: {e}", "error")

        return leads

    def run(self, bucket_name: str = None, max_queries: int = 5) -> Dict:
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

        try:
            for i, q in enumerate(queries, 1):
                self.log(f"\n[{i}/{len(queries)}] {q['query']}", "info")

                # Try multiple sources with fallback strategy
                query_leads = []

                # Source 1: Google Maps
                query_leads.extend(
                    self.scrape_google_maps(q["query"], q["bucket"], max_results=2)
                )

                # Source 2: JustDial
                if len(query_leads) < 3:
                    query_leads.extend(
                        self.scrape_justdial(
                            q["query"], q["bucket"], 3 - len(query_leads)
                        )
                    )

                # Source 3: IndiaMART
                if len(query_leads) < 3:
                    query_leads.extend(
                        self.scrape_indiamart(
                            q["query"], q["bucket"], 3 - len(query_leads)
                        )
                    )

                # Source 4: Yelp
                if len(query_leads) < 3:
                    query_leads.extend(
                        self.scrape_yelp(q["query"], q["bucket"], 3 - len(query_leads))
                    )

                # Source 5: Yellow Pages
                if len(query_leads) < 3:
                    query_leads.extend(
                        self.scrape_yellowpages(
                            q["query"], q["bucket"], 3 - len(query_leads)
                        )
                    )

                # Batch Save leads to database
                if query_leads:
                    saved = self.repo.save_leads_batch(query_leads)
                    total_saved += saved
                    total_leads += len(query_leads)
                    self.log(
                        f"  ✓ Found {len(query_leads)} leads, saved {saved}", "success"
                    )

                time.sleep(1)  # Minimal rate limiting since we reuse driver
        finally:
            self._quit_driver()

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
