import time
import random
from typing import List, Dict, Optional
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from scrapers.base_scraper import BaseScraper


class GoogleMapsScraper(BaseScraper):
    """Google Maps scraper using Selenium for web scraping"""

    def __init__(self):
        super().__init__("google_maps")
        self.wait = None

    def _init_driver(self, headless: bool = True):
        """Initialize the Selenium WebDriver"""
        if self.driver:
            return self.driver

        driver = super()._init_driver(headless=headless)
        if driver:
            self.wait = WebDriverWait(driver, 15)
        return driver

    def close(self):
        """Close the WebDriver"""
        self._close_driver()

    def search_places_selenium(
        self, query: str, location_hint: str = None
    ) -> List[Dict]:
        """Search for places using Google Maps website via Selenium"""
        self._init_driver()

        search_query = f"{query} {location_hint}" if location_hint else query
        print(f"Searching Google Maps for: {search_query}")

        try:
            self.driver.get(
                f"https://www.google.com/maps/search/{search_query.replace(' ', '+')}"
            )

            # Wait for results to load
            try:
                self.wait.until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, "div[role='feed']")
                    )
                )
            except Exception as e:
                print(f"Results feed not found: {e}. Trying alternative approach...")
                # Try to find results using different selectors
                try:
                    result_elements = self.driver.find_elements(
                        By.CSS_SELECTOR,
                        "div[data-result-index], a[href*='/maps/place/']",
                    )
                    if not result_elements:
                        print("No results found with alternative selectors either.")
                        return []
                except:
                    print(
                        "No results found. Query might be too specific or captcha appeared."
                    )
                    return []

            # Scroll to load more results
            feed = self.driver.find_element(By.CSS_SELECTOR, "div[role='feed']")
            last_height = self.driver.execute_script(
                "return arguments[0].scrollHeight", feed
            )

            # Scroll a few times to get more results
            for _ in range(3):
                self.driver.execute_script(
                    "arguments[0].scrollTop = arguments[0].scrollHeight", feed
                )
                time.sleep(2)
                new_height = self.driver.execute_script(
                    "return arguments[0].scrollHeight", feed
                )
                if new_height == last_height:
                    break
                last_height = new_height

            # Extract result links with multiple selector attempts
            selectors = [
                "a[href*='/maps/place/']",
                "div[data-result-index] a",
                "div[role='article'] a",
                "a[jsaction*='mouseover']",
            ]

            result_elements = []
            for selector in selectors:
                elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                if elements:
                    result_elements = elements
                    print(f"Found {len(elements)} results using selector: {selector}")
                    break

            if not result_elements:
                print("No results found with any selector")
                return []

            places = []
            seen_urls = set()

            for element in result_elements[
                :15
            ]:  # Limit to top 15 results for performance
                try:
                    url = element.get_attribute("href")
                    if url in seen_urls:
                        continue
                    seen_urls.add(url)

                    # Instead of clicking (which is slow), we can try to extract basic info from the list
                    # or navigate to each URL if more detail is needed.
                    # For now, let's extract what we can from the result card components.

                    element.find_element(By.XPATH, "./..")
                    # This is a bit fragile as Google changes classes often, but role='article' or similar usually holds data

                    name = element.get_attribute("aria-label")
                    if not name:
                        continue

                    # Basic data extraction from the list view
                    place_data = {
                        "name": name,
                        "url": url,
                    }

                    # We'll need to click or navigate to get phone and website reliably
                    # Let's navigate to the specific place URL
                    self.driver.execute_script(
                        "window.open(arguments[0], '_blank');", url
                    )
                    self.driver.switch_to.window(self.driver.window_handles[1])

                    # Wait for details to load
                    time.sleep(1.5)

                    details = self._extract_details()
                    if details:
                        place_data.update(details)

                    self.driver.close()
                    self.driver.switch_to.window(self.driver.window_handles[0])

                    processed_place = self._process_place_data(place_data, query)
                    if processed_place:
                        places.append(processed_place)

                except Exception as e:
                    print(f"Error processing a result: {e}")
                    if len(self.driver.window_handles) > 1:
                        self.driver.close()
                        self.driver.switch_to.window(self.driver.window_handles[0])
                    continue

            return places

        except Exception as e:
            print(f"Selenium search failed: {e}")
            return []

    def _extract_details(self) -> Dict:
        """Extract details from the place detail view"""
        details = {}
        try:
            # Website
            try:
                website_el = self.driver.find_element(
                    By.CSS_SELECTOR,
                    "a[aria-label*='Website'], a[data-item-id='authority']",
                )
                details["website"] = website_el.get_attribute("href")
            except:
                details["website"] = ""

            # Phone
            try:
                phone_el = self.driver.find_element(
                    By.CSS_SELECTOR,
                    "button[data-tooltip*='Copy phone number'], button[aria-label*='Phone']",
                )
                details["phone"] = (
                    phone_el.get_attribute("aria-label").replace("Phone: ", "").strip()
                )
            except:
                details["phone"] = ""

            # Address
            try:
                address_el = self.driver.find_element(
                    By.CSS_SELECTOR, "button[data-item-id='address']"
                )
                details["address"] = address_el.text.strip()
            except:
                details["address"] = ""

            # Rating
            try:
                rating_el = self.driver.find_element(
                    By.CSS_SELECTOR, "span[aria-hidden='true']"
                )
                details["rating"] = float(rating_el.text.strip())
            except:
                details["rating"] = 0

            return details
        except Exception as e:
            print(f"Error extracting details: {e}")
            return details

    def _process_place_data(self, place: Dict, search_query: str) -> Optional[Dict]:
        """Process and validate place data"""
        try:
            website = place.get("website", "")

            # Allow businesses without websites for demo (comment out for production)
            # if not website:
            #     return None

            name = place.get("name", "")
            address = place.get("address", "")
            phone = place.get("phone", "")
            rating = place.get("rating", 0)

            # Extract city from address
            city = self.extract_city_from_text(address)

            # Determine category
            category = self.determine_category(
                f"{search_query} {name}", default="Local Service Provider"
            )

            # Calculate quality score
            quality_score = self.calculate_quality_score(
                {
                    "category": category,
                    "location": city,
                    "website": website,
                    "phone": phone,
                }
            )

            return {
                "business_name": name,
                "address": address,
                "city": city,
                "phone": phone,
                "website": website,
                "category": category,
                "rating": rating,
                "source": "google_maps_selenium",
                "quality_score": quality_score,
                "search_query": search_query,
            }

        except Exception as e:
            print(f"Error processing place data: {e}")
            return None

    def scrape_by_buckets(
        self, max_queries_per_bucket: int = 10, plan: List[Dict] = None
    ) -> List[Dict]:
        """Scrape leads based on bucket definitions using Selenium"""
        all_leads = []

        # Use provided plan or fall back to generating one locally
        queries = plan if plan else self.bucket_manager.get_search_queries()

        # Filter logic is only needed if we are generating our own queries
        # If plan is provided, we assume it's already filtered/ prioritized by Stage 0
        filtered_queries = []

        if plan:
            filtered_queries = plan
            print(
                f"Executing {len(filtered_queries)} search queries from provided plan..."
            )
        else:
            # Limit queries per bucket for testing
            bucket_query_counts = {}
            filtered_queries = []

            for query in queries:
                bucket = query["bucket"]
                if bucket not in bucket_query_counts:
                    bucket_query_counts[bucket] = 0

                if bucket_query_counts[bucket] < max_queries_per_bucket:
                    filtered_queries.append(query)
                    bucket_query_counts[bucket] += 1
            print(
                f"Executing {len(filtered_queries)} search queries using Selenium (Local Plan)..."
            )

        try:
            for i, query in enumerate(filtered_queries):
                # Handle both 'city' and 'location' keys if present
                city = query.get("city") or query.get("location", "Unknown")
                print(
                    f"\n[{i + 1}/{len(filtered_queries)}] Searching: {query['query']} in {city}"
                )

                places = self.search_places_selenium(
                    query=query["query"], location_hint=city
                )

                new_leads_from_query = []
                for place in places:
                    # Add bucket information
                    place["bucket"] = query.get("bucket", "")
                    place["tier"] = query.get("tier", "")
                    place["priority"] = query.get("priority", "")
                    new_leads_from_query.append(place)
                    all_leads.append(place)

                print(f"  Found {len(places)} places")

                # Save batch to database immediately to prevent data loss on crash
                if new_leads_from_query:
                    self.save_to_database(new_leads_from_query)

                # Delay between queries
                if i < len(filtered_queries) - 1:
                    time.sleep(random.uniform(5, 10))
        finally:
            self.close()

        return all_leads
