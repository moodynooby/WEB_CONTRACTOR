"""Discovery Module: Query Generation + Lead Scraping (Stage 0 + Stage A)"""
import json
import time
import requests
from typing import List, Dict
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from lead_repository import LeadRepository


class Discovery:
    """Consolidated Stage 0 (Planning) + Stage A (Scraping)"""

    def __init__(self, repo=None, logger=None):
        self.repo = repo or LeadRepository()
        self.buckets = self._load_buckets()
        self.logger = logger
        self.ollama_url = "http://localhost:11434"
        self.ollama_enabled = self._test_ollama()

    def _test_ollama(self) -> bool:
        """Test Ollama connection"""
        try:
            response = requests.get(f"{self.ollama_url}/api/tags", timeout=5)
            return response.status_code == 200
        except:
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
        Categories: {bucket.get('categories', [])}
        Search Patterns: {bucket.get('search_patterns', [])}

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
                    "model": "qwen2.5:latest",
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",
                    "system": "You are a market research assistant. Output ONLY valid JSON."
                },
                timeout=30
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
                    "model": "qwen2.5:latest",
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",
                    "system": "You are a business strategist. Output ONLY valid JSON."
                },
                timeout=30
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
        buckets = [b for b in self.buckets if not bucket_name or b["name"] == bucket_name]
        
        # Load geographic focus from DB
        geo_focus = self.repo.get_config("geographic_focus") or {}

        for bucket in buckets:
            search_patterns = bucket.get("search_patterns", [])
            # Handle if search_patterns is string (should be parsed by repo, but safety check)
            if isinstance(search_patterns, str):
                 try: search_patterns = json.loads(search_patterns)
                 except: search_patterns = []

            for pattern in search_patterns[:3]:
                # Get cities from geographic segments
                cities = []
                segments = bucket.get("geographic_segments", [])
                if isinstance(segments, str):
                    try: segments = json.loads(segments)
                    except: segments = []
                    
                for seg_name in segments:
                    if seg_name in geo_focus:
                        cities.extend(geo_focus[seg_name].get("cities", [])[:2])
                
                if not cities:
                    cities = ["Mumbai", "Delhi", "Bangalore"]

                for city in cities[:2]:
                    query = pattern.replace("{city}", city)
                    queries.append({
                        "query": query,
                        "bucket": bucket["name"],
                        "city": city
                    })
                    if len(queries) >= limit:
                        return queries

        return queries[:limit]

    def scrape_google_maps(self, query: str, bucket: str, max_results: int = 5) -> List[Dict]:
        """Scrape Google Maps for business leads"""
        leads = []
        
        try:
            chrome_options = Options()
            chrome_options.add_argument("--headless")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-gpu")
            
            driver = webdriver.Chrome(options=chrome_options)
            driver.set_page_load_timeout(30)
            
            search_url = f"https://www.google.com/maps/search/{query.replace(' ', '+')}"
            driver.get(search_url)
            time.sleep(3)

            # Wait for results
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "a[href*='/maps/place/']"))
                )
            except:
                driver.quit()
                return leads

            # Get business listings
            business_elements = driver.find_elements(By.CSS_SELECTOR, "a[href*='/maps/place/']")[:max_results]

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
                        website_element = driver.find_element(By.CSS_SELECTOR, "a[data-item-id*='authority']")
                        website = website_element.get_attribute("href")
                    except:
                        pass

                    # Extract phone
                    phone = None
                    try:
                        phone_element = driver.find_element(By.CSS_SELECTOR, "button[data-item-id*='phone']")
                        phone = phone_element.get_attribute("aria-label")
                    except:
                        pass

                    if name and website:
                        leads.append({
                            "business_name": name,
                            "website": website,
                            "phone": phone,
                            "source": "google_maps",
                            "bucket": bucket,
                            "category": query.split()[0],
                            "location": query.split()[-1] if " " in query else "Unknown"
                        })

                except Exception as e:
                    continue

            driver.quit()

        except Exception as e:
            self.log(f"Error scraping Google Maps: {e}", "error")

        return leads

    def scrape_yellow_pages(self, query: str, bucket: str, max_results: int = 5) -> List[Dict]:
        """Scrape Yellow Pages for business leads"""
        leads = []
        
        try:
            # Parse query to extract category and location
            parts = query.split()
            category = " ".join(parts[:-1]) if len(parts) > 1 else query
            location = parts[-1] if len(parts) > 1 else "India"
            
            # Yellow Pages India URL structure
            search_term = category.replace(" ", "-").lower()
            url = f"https://www.yellowpages.in/search/{search_term}/all-india"
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code != 200:
                return leads

            soup = BeautifulSoup(response.content, "html.parser")
            
            # Find business listings
            listings = soup.find_all("div", class_="row srp-list", limit=max_results)
            
            for listing in listings:
                try:
                    # Business name
                    name_elem = listing.find("a", class_="title")
                    name = name_elem.text.strip() if name_elem else None
                    
                    # Website
                    website_elem = listing.find("a", href=True, title="Website")
                    website = website_elem["href"] if website_elem else None
                    
                    # Phone
                    phone_elem = listing.find("span", class_="mobilenum")
                    phone = phone_elem.text.strip() if phone_elem else None
                    
                    if name and website:
                        leads.append({
                            "business_name": name,
                            "website": website,
                            "phone": phone,
                            "source": "yellow_pages",
                            "bucket": bucket,
                            "category": category,
                            "location": location
                        })
                        
                except Exception as e:
                    continue
                    
        except Exception as e:
            self.log(f"Error scraping Yellow Pages: {e}", "error")
            
        return leads

    def run(self, bucket_name: str = None, max_queries: int = 5) -> Dict:
        """Execute full discovery pipeline with automatic expansion"""
        self.buckets = self._load_buckets()
        self.log(f"\n{'='*60}")
        self.log("DISCOVERY: Query Generation + Lead Scraping")
        self.log(f"{'='*60}")
        
        # Stage 0: Generate queries
        queries = self.generate_queries(bucket_name, max_queries)
        self.log(f"Generated {len(queries)} search queries", "info")
        
        # Stage A: Scrape leads
        total_leads = 0
        total_saved = 0
        
        for i, q in enumerate(queries, 1):
            self.log(f"\n[{i}/{len(queries)}] {q['query']}", "info")
            
            # Try Google Maps first
            leads = self.scrape_google_maps(q["query"], q["bucket"], max_results=3)
            
            # Try Yellow Pages if Google Maps returns nothing
            if not leads:
                leads = self.scrape_yellow_pages(q["query"], q["bucket"], max_results=3)
            
            # Save leads to database
            query_saved = 0
            for lead in leads:
                lead_id = self.repo.save_lead(lead)
                if lead_id > 0:
                    query_saved += 1
                    self.log(f"  ✓ {lead['business_name']}", "success")
            
            # Automatic expansion trigger: If we found no NEW leads for this query
            if query_saved == 0 and self.ollama_enabled:
                self.log(f"  ℹ No new leads found for '{q['query']}'. Recommendation: Press [x] to expand markets.", "info")

            total_saved += query_saved
            total_leads += len(leads)
            time.sleep(2)  # Rate limiting
        
        self.log(f"\n{'='*60}")
        self.log(f"Discovery Complete: {total_leads} found, {total_saved} saved", "success")
        self.log(f"{'='*60}\n")
        
        return {
            "queries_executed": len(queries),
            "leads_found": total_leads,
            "leads_saved": total_saved
        }
