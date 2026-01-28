"""
Facebook Business Pages Scraper using Selenium
Finds business pages through public search and extracts basic info
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import time
import random
import re
from typing import List, Dict, Optional
from urllib.parse import quote
from scrapers.base_scraper import BaseScraper

class FacebookScraper(BaseScraper):
    """Facebook Business Pages scraper using Selenium automation"""
    
    def __init__(self, headless: bool = True):
        super().__init__('facebook')
        self.headless = headless
        self.driver = None
        self.base_url = "https://www.facebook.com"
        
    def _setup_driver(self) -> webdriver.Chrome:
        """Setup Chrome WebDriver with options"""
        chrome_options = Options()
        if self.headless:
            chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        
        # Specific Facebook user agent
        chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36")
        
        try:
            driver = webdriver.Chrome(options=chrome_options)
            driver.set_page_load_timeout(30)
            return driver
        except Exception as e:
            print(f"Failed to setup WebDriver: {e}")
            return None

    def _scrape_web_fallback(self, query: str) -> List[Dict]:
        """Scrape Facebook search results for pages"""
        if not self.driver:
            self.driver = self._setup_driver()
            if not self.driver:
                return []

        try:
            encoded_query = quote(query)
            # Facebook page search URL pattern
            search_url = f"https://www.facebook.com/search/pages/?q={encoded_query}"
            
            self.rate_limiter.wait_if_needed()
            self.driver.get(search_url)
            
            # Wait for results
            try:
                WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "div[role='feed'], div[aria-label='Search Results']"))
                )
            except TimeoutException:
                print(f"  ✗ Timeout waiting for results for query: {query}")
                return []

            # Scroll to load a few results
            for _ in range(2):
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(random.uniform(2, 4))

            # Find page elements (Facebook uses dynamic classes, but role='article' or specific child structures are common)
            # This is a generic approach for public search
            page_elements = self.driver.find_elements(By.CSS_SELECTOR, "div[role='article']")
            
            leads = []
            for elem in page_elements[:15]:  # Limit per query
                try:
                    lead = self._parse_page_element(elem, query)
                    if lead:
                        leads.append(lead)
                except Exception:
                    continue
                    
            return leads

        except Exception as e:
            print(f"  ✗ Error scraping Facebook web: {e}")
            return []

    def _parse_page_element(self, element, query_text: str) -> Optional[Dict]:
        """Parse individual page item from search results"""
        try:
            # Facebook's DOM is complex; these selectors might need refinement
            # Look for titles/links
            link_elem = element.find_element(By.CSS_SELECTOR, "a[role='link']")
            name = link_elem.text.strip()
            page_url = link_elem.get_attribute('href')
            
            if not name or not page_url:
                return None
                
            # Basic info often appears in spans
            info_text = element.text
            
            # Use BaseScraper to determine data
            # In web results, we often don't have direct phone/website without visiting
            # For now, we capture what's visible
            
            # Determine category (often mentioned in search results)
            # Default to query's category if not found
            category = self.determine_category(info_text, default='Business')
            
            # Calculate quality score
            lead_data = {
                'business_name': name,
                'category': category,
                'source': 'facebook',
                'facebook_url': page_url
            }
            
            quality_score = self.calculate_quality_score(lead_data)
            
            return {
                'business_name': name,
                'category': category,
                'location': 'Unknown',
                'website': '', # Would require visiting page
                'source': 'facebook',
                'facebook_url': page_url,
                'quality_score': quality_score
            }
        except Exception:
            return None

    def scrape_by_buckets(self, max_queries: int = 15) -> List[Dict]:
        """Main scraping function for Facebook using discovery plan"""
        self.driver = self._setup_driver()
        if not self.driver:
            return []
            
        all_leads = []
        try:
            queries = self.bucket_manager.get_search_queries()
            targeted_queries = queries[:max_queries]
            
            print(f"Executing {len(targeted_queries)} Facebook searches...")
            
            for i, query in enumerate(targeted_queries):
                print(f"\n[{i+1}/{len(targeted_queries)}] Searching: {query['query']}")
                leads = self._scrape_web_fallback(query['query'])
                
                # Enrich with query data
                for lead in leads:
                    lead['bucket'] = query.get('bucket', '')
                    lead['category'] = query.get('category', lead['category'])
                    lead['location'] = lead.get('location') if lead.get('location') != 'Unknown' else query.get('city', 'Unknown')
                    
                all_leads.extend(leads)
                if leads:
                    print(f"  ✓ Found {len(leads)} Facebook pages")
                    
                if i < len(targeted_queries) - 1:
                    time.sleep(random.uniform(5, 10))
                    
        finally:
            if self.driver:
                self.driver.quit()
                
        return all_leads

if __name__ == '__main__':
    scraper = FacebookScraper(headless=True)
    print("=== FACEBOOK BUSINESS PAGES SCRAPER ===")
    leads = scraper.scrape_by_buckets(max_queries=2)
    if leads:
        print(f"\nFound {len(leads)} total leads")
        scraper.save_to_database(leads)
    else:
        print("No leads found.")
