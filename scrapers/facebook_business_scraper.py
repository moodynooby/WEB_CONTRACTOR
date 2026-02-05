"""
Facebook Business Scraper
Social proof and contact information from Facebook Pages
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


class FacebookBusinessScraper(BaseScraper):
    """Facebook business page scraper for local businesses"""

    def __init__(self):
        super().__init__("facebook_business")
        self.base_url = "https://www.facebook.com"
        
    def search_businesses(
        self, query: str, location: str, max_results: int = 25
    ) -> List[Dict]:
        """Search for businesses on Facebook"""
        self._init_driver()
        all_results = []
        
        search_query = f"{query} {location}".strip()
        print(f"Searching Facebook for: {search_query}")
        
        try:
            # Navigate to Facebook search (Note: Facebook has strong anti-bot measures)
            search_url = f"{self.base_url}/search/pages/?q={search_query.replace(' ', '%20')}"
            self.driver.get(search_url)
            
            # Wait for search results
            try:
                WebDriverWait(self.driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "[role='article'], .page, .business-page"))
                )
            except TimeoutException:
                print("No results found or timeout occurred")
                return []
            
            # Extract business page listings
            listings = self.driver.find_elements(
                By.CSS_SELECTOR, 
                "[role='article'], .page, .business-page, [data-testid='page']"
            )[:max_results]
            
            for listing in listings:
                try:
                    business_data = self._parse_facebook_listing(listing, query, location)
                    if business_data:
                        all_results.append(business_data)
                except Exception as e:
                    print(f"Error parsing Facebook listing: {e}")
                    continue
            
            print(f"Found {len(all_results)} Facebook business pages")
            return all_results
            
        except Exception as e:
            print(f"Facebook search failed: {e}")
            return []
        
        finally:
            if self.driver:
                self.driver.quit()
    
    def _parse_facebook_listing(self, listing, query: str, location: str) -> Optional[Dict]:
        """Parse individual Facebook business listing"""
        try:
            # Business name
            try:
                name_elem = listing.find_element(
                    By.CSS_SELECTOR, 
                    "h2 a, h3 a, .page-name, .business-name, [data-testid='page-name']"
                )
                business_name = name_elem.text.strip()
                page_url = name_elem.get_attribute("href")
            except NoSuchElementException:
                return None
            
            # Page category
            try:
                category_elem = listing.find_element(
                    By.CSS_SELECTOR, 
                    ".category, .page-category, .business-type"
                )
                category = category_elem.text.strip()
            except NoSuchElementException:
                category = self.determine_category(f"{query} {business_name}")
            
            # Page rating (if available)
            try:
                rating_elem = listing.find_element(
                    By.CSS_SELECTOR, 
                    ".rating, .review-score, .stars"
                )
                rating_text = rating_elem.text.strip()
                rating_match = re.search(r'(\d+\.?\d*)', rating_text)
                facebook_rating = float(rating_match.group(1)) if rating_match else 0
            except NoSuchElementException:
                facebook_rating = 0
            
            # Follower count (social proof)
            try:
                followers_elem = listing.find_element(
                    By.CSS_SELECTOR, 
                    ".followers, .likes, .follow-count"
                )
                followers_text = followers_elem.text.strip()
                follower_count = int(re.search(r'([\d,]+)', followers_text).group(1).replace(',', '')) if re.search(r'([\d,]+)', followers_text) else 0
            except NoSuchElementException:
                follower_count = 0
            
            # Verify button (indicates authenticity)
            is_verified = bool(listing.find_elements(
                By.CSS_SELECTOR, 
                ".verified, .verified-badge"
            ))
            
            # Contact information (phone, website) - often requires clicking into page
            phone = ""
            website = ""
            address = ""
            
            # Try to find contact info in the listing
            try:
                contact_info = listing.find_elements(
                    By.CSS_SELECTOR, 
                    ".contact-info, .phone, .website, .address"
                )
                for info in contact_info:
                    info_text = info.text.strip().lower()
                    if 'phone' in info_text or re.search(r'\(\d{3}\)|\d{3}-\d{3}-\d{4}', info_text):
                        phone = info.text.strip()
                    elif 'website' in info_text or info_text.startswith('http'):
                        website = info.text.strip()
                    elif 'address' in info_text:
                        address = info.text.strip()
            except:
                pass
            
            # Extract city from address or location
            city = self.extract_city_from_text(address, location)
            
            # Calculate quality score with Facebook-specific factors
            quality_score = self.calculate_quality_score({
                "category": category,
                "location": city,
                "website": website,
                "phone": phone,
            })
            
            # Bonus points for verification and social proof
            if is_verified:
                quality_score += 0.15
            
            if follower_count >= 1000:
                quality_score += 0.1
            elif follower_count >= 500:
                quality_score += 0.05
            
            if facebook_rating >= 4.0:
                quality_score += 0.1
            
            # Ensure score doesn't exceed 1.0
            quality_score = min(quality_score, 1.0)
            
            # Determine tier based on verification and social metrics
            if is_verified and follower_count >= 1000:
                tier = "verified_social"
            elif follower_count >= 500:
                tier = "established"
            else:
                tier = "standard"
            
            # Determine priority
            if is_verified and follower_count >= 1000:
                priority = "high"
            elif is_verified or follower_count >= 500:
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
                "source": "facebook_business",
                "quality_score": quality_score,
                "facebook_rating": facebook_rating,
                "follower_count": follower_count,
                "is_verified": is_verified,
                "search_query": query,
                "facebook_url": page_url,
                "bucket": "",
                "tier": tier,
                "priority": priority,
            }
            
        except Exception as e:
            print(f"Error parsing Facebook listing: {e}")
            return None
    
    def scrape_by_buckets(self, max_queries_per_bucket: int = 15) -> List[Dict]:
        """Scrape Facebook for all bucket queries"""
        all_leads = []
        queries = self.bucket_manager.get_search_queries()
        
        print(f"Starting Facebook Business scraping with {len(queries)} queries...")
        
        for i, query in enumerate(queries):
            city = query.get("city", query.get("location", "Unknown"))
            print(f"\n[{i+1}/{len(queries)}] Searching Facebook for: {query['query']} in {city}")
            
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
            
            print(f"  Found {len(results)} Facebook business pages")
            
            # Save batch to database
            if results:
                self.save_to_database(results)
            
            # Delay between queries (Facebook has strong rate limiting)
            if i < len(queries) - 1:
                time.sleep(random.uniform(15, 25))  # Longer delay for Facebook
        
        return all_leads