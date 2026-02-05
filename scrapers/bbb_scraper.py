"""
Better Business Bureau (BBB) Scraper
High-quality, verified business listings with accreditation data
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


class BBBScraper(BaseScraper):
    """Better Business Bureau scraper for verified business leads"""

    def __init__(self):
        super().__init__("better_business_bureau")
        self.base_url = "https://www.bbb.org"
        
    def search_businesses(
        self, query: str, location: str, max_results: int = 20
    ) -> List[Dict]:
        """Search for businesses on BBB"""
        self._init_driver()
        all_results = []
        
        search_query = f"{query} {location}".strip()
        print(f"Searching BBB for: {search_query}")
        
        try:
            # Navigate to BBB search
            search_url = f"{self.base_url}/search?find_country=US&find_loc={location}&find_text={query}"
            self.driver.get(search_url)
            
            # Wait for results
            try:
                WebDriverWait(self.driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, ".search-result, .result-item"))
                )
            except TimeoutException:
                print("No results found or timeout occurred")
                return []
            
            # Extract business listings
            listings = self.driver.find_elements(
                By.CSS_SELECTOR, 
                ".search-result, .result-item, .business-card"
            )[:max_results]
            
            for listing in listings[:max_results]:
                try:
                    business_data = self._parse_bbb_listing(listing, query, location)
                    if business_data:
                        all_results.append(business_data)
                except Exception as e:
                    print(f"Error parsing BBB listing: {e}")
                    continue
            
            print(f"Found {len(all_results)} verified businesses on BBB")
            return all_results
            
        except Exception as e:
            print(f"BBB search failed: {e}")
            return []
        
        finally:
            if self.driver:
                self.driver.quit()
    
    def _parse_bbb_listing(self, listing, query: str, location: str) -> Optional[Dict]:
        """Parse individual BBB business listing"""
        try:
            # Business name
            try:
                name_elem = listing.find_element(
                    By.CSS_SELECTOR, 
                    "h2 a, .business-name, .result-title, .name"
                )
                business_name = name_elem.text.strip()
                business_url = name_elem.get_attribute("href")
            except NoSuchElementException:
                return None
            
            # BBB rating and accreditation
            try:
                rating_elem = listing.find_element(
                    By.CSS_SELECTOR, 
                    ".rating, .bbb-rating, .score"
                )
                rating_text = rating_elem.text.strip()
                # Extract numeric rating
                rating_match = re.search(r'(\d+\.?\d*)', rating_text)
                bbb_rating = float(rating_match.group(1)) if rating_match else 0
            except NoSuchElementException:
                bbb_rating = 0
            
            # Check if accredited
            is_accredited = bool(listing.find_elements(
                By.CSS_SELECTOR, 
                ".accredited, .accreditation-badge, .bbb-accredited"
            ))
            
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
                    "a[href^='http']:not([href*='bbb.org'])"
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
            
            # Calculate quality score (BBB accreditation increases quality)
            quality_score = self.calculate_quality_score({
                "category": category,
                "location": city,
                "website": website,
                "phone": phone,
            })
            
            # Bonus points for BBB accreditation
            if is_accredited:
                quality_score += 0.2
            
            # Ensure score doesn't exceed 1.0
            quality_score = min(quality_score, 1.0)
            
            return {
                "business_name": business_name,
                "phone": phone,
                "website": website,
                "address": address,
                "city": city,
                "category": category,
                "source": "bbb",
                "quality_score": quality_score,
                "bbb_rating": bbb_rating,
                "accredited": is_accredited,
                "search_query": query,
                "bbb_url": business_url,
                "bucket": "",
                "tier": "verified" if is_accredited else "unverified",
                "priority": "high" if is_accredited else "medium",
            }
            
        except Exception as e:
            print(f"Error parsing BBB listing: {e}")
            return None
    
    def scrape_by_buckets(self, max_queries_per_bucket: int = 15) -> List[Dict]:
        """Scrape BBB for all bucket queries"""
        all_leads = []
        queries = self.bucket_manager.get_search_queries()
        
        print(f"Starting BBB scraping with {len(queries)} queries...")
        
        for i, query in enumerate(queries):
            city = query.get("city", query.get("location", "Unknown"))
            print(f"\n[{i+1}/{len(queries)}] Searching BBB for: {query['query']} in {city}")
            
            results = self.search_businesses(
                query=query["query"], 
                location=city, 
                max_results=15
            )
            
            # Add bucket metadata
            for result in results:
                result["bucket"] = query.get("bucket", "")
                result["tier"] = query.get("tier", "")
                result["priority"] = query.get("priority", "")
                all_leads.append(result)
            
            print(f"  Found {len(results)} BBB verified businesses")
            
            # Save batch to database
            if results:
                self.save_to_database(results)
            
            # Delay between queries
            if i < len(queries) - 1:
                time.sleep(random.uniform(8, 15))  # Longer delay for BBB
        
        return all_leads