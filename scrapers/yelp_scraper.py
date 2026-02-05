"""
Yelp Business Scraper
Excellent for local services with review data and social proof
"""

import time
import random
import re
from typing import List, Dict, Optional
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from scrapers.base_scraper import BaseScraper


class YelpScraper(BaseScraper):
    """Yelp business scraper for local service providers"""

    def __init__(self):
        super().__init__("yelp")
        self.base_url = "https://www.yelp.com"
        
    def search_businesses(
        self, query: str, location: str, max_results: int = 25
    ) -> List[Dict]:
        """Search for businesses on Yelp"""
        self._init_driver()
        all_results = []
        
        search_query = f"{query} {location}".strip()
        print(f"Searching Yelp for: {search_query}")
        
        try:
            # Navigate to Yelp search
            search_url = f"{self.base_url}/search?find_desc={query}&find_loc={location}"
            self.driver.get(search_url)
            
            # Wait for search results
            try:
                WebDriverWait(self.driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "[data-testid='search-result'], .result, .business-container"))
                )
            except TimeoutException:
                print("No results found or timeout occurred")
                return []
            
            # Handle potential "Are you human?" CAPTCHA
            if self._check_captcha():
                print("CAPTCHA detected, waiting for manual resolution...")
                input("Press Enter after solving CAPTCHA...")
            
            # Extract business listings
            listings = self.driver.find_elements(
                By.CSS_SELECTOR, 
                "[data-testid='search-result'], .result, .business-container"
            )[:max_results]
            
            for listing in listings:
                try:
                    business_data = self._parse_yelp_listing(listing, query, location)
                    if business_data:
                        all_results.append(business_data)
                except Exception as e:
                    print(f"Error parsing Yelp listing: {e}")
                    continue
            
            print(f"Found {len(all_results)} businesses on Yelp")
            return all_results
            
        except Exception as e:
            print(f"Yelp search failed: {e}")
            return []
        
        finally:
            if self.driver:
                self.driver.quit()
    
    def _check_captcha(self) -> bool:
        """Check if CAPTCHA is present"""
        try:
            captcha_elements = self.driver.find_elements(
                By.CSS_SELECTOR, 
                ".captcha, #captcha, .g-recaptcha"
            )
            return len(captcha_elements) > 0
        except:
            return False
    
    def _parse_yelp_listing(self, listing, query: str, location: str) -> Optional[Dict]:
        """Parse individual Yelp business listing"""
        try:
            # Business name
            try:
                name_elem = listing.find_element(
                    By.CSS_SELECTOR, 
                    "h3 a, .business-name, .result-name, .name"
                )
                business_name = name_elem.text.strip()
                business_url = name_elem.get_attribute("href")
            except NoSuchElementException:
                return None
            
            # Yelp rating and review count
            try:
                rating_elem = listing.find_element(
                    By.CSS_SELECTOR, 
                    ".rating, .stars, .yelp-rating"
                )
                rating_text = rating_elem.get_attribute("aria-label") or rating_elem.text
                # Extract numeric rating
                rating_match = re.search(r'(\d+\.?\d*)', rating_text)
                yelp_rating = float(rating_match.group(1)) if rating_match else 0
            except NoSuchElementException:
                yelp_rating = 0
            
            # Review count
            try:
                reviews_elem = listing.find_element(
                    By.CSS_SELECTOR, 
                    ".review-count, .reviews, .count"
                )
                review_text = reviews_elem.text.strip()
                review_count = int(re.search(r'(\d+)', review_text).group(1)) if re.search(r'(\d+)', review_text) else 0
            except NoSuchElementException:
                review_count = 0
            
            # Price range
            try:
                price_elem = listing.find_element(
                    By.CSS_SELECTOR, 
                    ".price, .price-range, .cost"
                )
                price_range = price_elem.text.strip()
            except NoSuchElementException:
                price_range = ""
            
            # Phone number
            try:
                phone_elem = listing.find_element(
                    By.CSS_SELECTOR, 
                    ".phone, .contact-phone, .telephone"
                )
                phone = re.sub(r'[^\d+()-]', '', phone_elem.text.strip())
            except NoSuchElementException:
                phone = ""
            
            # Address
            try:
                address_elem = listing.find_element(
                    By.CSS_SELECTOR, 
                    ".address, .location, .street-address"
                )
                address = address_elem.text.strip()
            except NoSuchElementException:
                address = ""
            
            # Website
            website = ""
            try:
                website_links = listing.find_elements(
                    By.CSS_SELECTOR, 
                    "a[href^='http']:not([href*='yelp.com'])"
                )
                if website_links:
                    website = website_links[0].get_attribute("href")
            except:
                pass
            
            # Category
            try:
                category_elem = listing.find_element(
                    By.CSS_SELECTOR, 
                    ".category, .business-type, .industry"
                )
                category = category_elem.text.strip()
            except NoSuchElementException:
                category = self.determine_category(f"{query} {business_name}")
            
            # Extract city from address
            city = self.extract_city_from_text(address, location)
            
            # Calculate quality score with Yelp-specific factors
            quality_score = self.calculate_quality_score({
                "category": category,
                "location": city,
                "website": website,
                "phone": phone,
            })
            
            # Bonus points for high Yelp rating and reviews
            if yelp_rating >= 4.0:
                quality_score += 0.15
            elif yelp_rating >= 3.5:
                quality_score += 0.1
            
            if review_count >= 50:
                quality_score += 0.1
            elif review_count >= 20:
                quality_score += 0.05
            
            # Ensure score doesn't exceed 1.0
            quality_score = min(quality_score, 1.0)
            
            # Determine tier based on rating and reviews
            if yelp_rating >= 4.5 and review_count >= 20:
                tier = "premium"
            elif yelp_rating >= 4.0:
                tier = "verified"
            else:
                tier = "standard"
            
            # Determine priority
            if yelp_rating >= 4.5 and review_count >= 100:
                priority = "high"
            elif yelp_rating >= 4.0:
                priority = "medium"
            else:
                priority = "low"
            
            return {
                "business_name": business_name,
                "phone": phone,
                "website": website,
                "address": address,
                "city": city,
                "category": category,
                "source": "yelp",
                "quality_score": quality_score,
                "yelp_rating": yelp_rating,
                "review_count": review_count,
                "price_range": price_range,
                "search_query": query,
                "yelp_url": business_url,
                "bucket": "",
                "tier": tier,
                "priority": priority,
            }
            
        except Exception as e:
            print(f"Error parsing Yelp listing: {e}")
            return None
    
    def scrape_by_buckets(self, max_queries_per_bucket: int = 20) -> List[Dict]:
        """Scrape Yelp for all bucket queries"""
        all_leads = []
        queries = self.bucket_manager.get_search_queries()
        
        print(f"Starting Yelp scraping with {len(queries)} queries...")
        
        for i, query in enumerate(queries):
            city = query.get("city", query.get("location", "Unknown"))
            print(f"\n[{i+1}/{len(queries)}] Searching Yelp for: {query['query']} in {city}")
            
            results = self.search_businesses(
                query=query["query"], 
                location=city, 
                max_results=20
            )
            
            # Add bucket metadata
            for result in results:
                result["bucket"] = query.get("bucket", "")
                result["tier"] = query.get("tier", "")
                result["priority"] = query.get("priority", "")
                all_leads.append(result)
            
            print(f"  Found {len(results)} Yelp businesses")
            
            # Save batch to database
            if results:
                self.save_to_database(results)
            
            # Delay between queries
            if i < len(queries) - 1:
                time.sleep(random.uniform(10, 20))  # Longer delay for Yelp
        
        return all_leads