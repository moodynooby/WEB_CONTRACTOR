"""
Yellow Pages Scraper using Selenium
Scrapes business leads from local directories
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
from core.selenium_utils import SeleniumDriverFactory

class YellowPagesScraper(BaseScraper):
    """Enhanced Yellow Pages scraper using Selenium automation"""
    
    def __init__(self, headless: bool = True):
        super().__init__('yellow_pages')
        self.headless = headless
        self.driver = None
        
    def _setup_driver(self) -> webdriver.Chrome:
        """Setup Chrome WebDriver with options"""
        return SeleniumDriverFactory.create_driver(headless=self.headless)

    def scrape_yellow_directory(self, max_queries: int = 20) -> List[Dict]:
        """Main scraping function for Yellow Pages using discovery plan"""
        self.driver = self._setup_driver()
        if not self.driver:
            return []
            
        all_leads = []
        try:
            queries = self.bucket_manager.get_search_queries()
            targeted_queries = queries[:max_queries]
            
            print(f"Executing {len(targeted_queries)} Yellow Pages searches...")
            
            for i, query in enumerate(targeted_queries):
                print(f"\n[{i+1}/{len(targeted_queries)}] Searching: {query['query']}")
                leads = self._scrape_directory(query)
                all_leads.extend(leads)
                
                if leads:
                    print(f"  ✓ Found {len(leads)} leads")
                    
                if i < len(targeted_queries) - 1:
                    time.sleep(random.uniform(5, 10))
                    
        finally:
            if self.driver:
                self.driver.quit()
                
        return all_leads

    def _scrape_directory(self, query: Dict) -> List[Dict]:
        """Scrape a specific directory using the query"""
        search_term = query['query']
        # Try a generic yellow pages search if specific URL fails
        search_url = f"https://www.yellowpages.in/search/{query['city'].lower()}/{search_term.replace(' ', '-')}"
        
        try:
            self.rate_limiter.wait_if_needed()
            self.driver.get(search_url)
            
            # Wait for results
            try:
                WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, ".listing, .result, .business-card"))
                )
            except TimeoutException:
                return []

            listings = self.driver.find_elements(By.CSS_SELECTOR, ".listing, .result, .business-card")
            leads = []
            
            for listing in listings[:20]:
                try:
                    lead = self._parse_listing(listing, query)
                    if lead:
                        leads.append(lead)
                except Exception:
                    continue
            return leads
            
        except Exception as e:
            print(f"  ✗ Error searching Yellow Pages: {e}")
            return []

    def _parse_listing(self, listing, query: Dict) -> Optional[Dict]:
        """Parse individual listing card"""
        try:
            # Dynamic selectors based on common patterns
            name = listing.find_element(By.CSS_SELECTOR, "h2, h3, .title, .name").text.strip()
            
            # Try to get website
            try:
                website = listing.find_element(By.CSS_SELECTOR, "a[href^='http']:not([href*='yellowpages'])").get_attribute('href')
            except:
                website = ''
                
            # Try to get phone
            try:
                phone = listing.find_element(By.CSS_SELECTOR, ".phone, .contact, .mobile").text.strip()
                phone = re.sub(r'[^\d+]', '', phone)
            except:
                phone = ''
                
            if not website and not phone:
                return None
                
            category = query['category']
            city = self.extract_city_from_text(listing.text, target_city=query.get('city'))
            
            quality_score = self.calculate_quality_score({
                'category': category,
                'location': city,
                'website': website,
                'phone': phone
            })
            
            return {
                'business_name': name,
                'phone': phone,
                'website': website,
                'location': city,
                'category': category,
                'source': 'yellow_pages',
                'quality_score': quality_score,
                'bucket': query.get('bucket', ''),
                'tier': query.get('tier', ''),
                'priority': query.get('priority', '')
            }
        except Exception:
            return None


