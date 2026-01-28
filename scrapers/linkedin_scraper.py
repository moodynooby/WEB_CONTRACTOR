"""
LinkedIn Company Scraper for B2B Professional Leads
Uses Selenium for robust scraping with rate limiting and ethical practices
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import time
import random
import json
import re
from typing import List, Dict, Optional
from urllib.parse import urlencode
from scrapers.base_scraper import BaseScraper

class LinkedInScraper(BaseScraper):
    """LinkedIn company scraper with Selenium automation"""
    
    def __init__(self, headless: bool = True):
        super().__init__('linkedin')
        self.driver = None
        self.headless = headless
        
        # LinkedIn specific settings
        self.linkedin_base_url = "https://www.linkedin.com"
        self.search_url = "https://www.linkedin.com/search/results/all/"

    def _setup_driver(self) -> webdriver.Chrome:
        """Setup Chrome WebDriver with options"""
        chrome_options = Options()
        
        if self.headless:
            chrome_options.add_argument("--headless")
        
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        
        # Random user agent
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        ]
        chrome_options.add_argument(f"--user-agent={random.choice(user_agents)}")
        
        try:
            driver = webdriver.Chrome(options=chrome_options)
            driver.set_page_load_timeout(30)
            return driver
        except Exception as e:
            print(f"Failed to setup WebDriver: {e}")
            print("Please ensure ChromeDriver is installed and accessible")
            return None
    
    def _random_scroll(self, driver: webdriver.Chrome, scrolls: int = 3):
        """Random scrolling to simulate human behavior"""
        for _ in range(scrolls):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(random.uniform(1, 2))
    
    def _extract_company_info(self, element, search_query: Dict) -> Optional[Dict]:
        """Extract company information from LinkedIn search result"""
        try:
            # Company name
            name_elem = element.find_element(By.CSS_SELECTOR, "span.entity-result__title-text")
            name = name_elem.text.strip() if name_elem else ''
            
            # Company description/industry
            desc_elem = element.find_element(By.CSS_SELECTOR, "div.entity-result__primary-subtitle")
            description = desc_elem.text.strip() if desc_elem else ''
            
            # Location
            location_elem = element.find_element(By.CSS_SELECTOR, "div.entity-result__secondary-subtitle")
            location = location_elem.text.strip() if location_elem else ''
            
            # Try to get company link
            link_elem = element.find_element(By.CSS_SELECTOR, "a.app-aware-link")
            company_url = link_elem.get_attribute('href') if link_elem else ''
            
            # Extract city from location using BaseScraper
            city = self.extract_city_from_text(location, target_city=search_query.get('city'))
            
            # Use category from query
            category = search_query['category']
            
            # Try to visit company page for website
            website = self._extract_company_website(company_url) if company_url else ''
            
            # Skip if no website
            if not website:
                return None
            
            # Calculate quality score using BaseScraper
            quality_score = self.calculate_quality_score({
                'category': category,
                'location': city,
                'website': website,
                'phone': ''  # LinkedIn rarely shows phone numbers
            })
            
            return {
                'business_name': name,
                'description': description,
                'location': location,
                'city': city,
                'website': website,
                'category': category,
                'linkedin_url': company_url,
                'source': 'linkedin',
                'quality_score': quality_score,
                'bucket': search_query.get('bucket', ''),
                'tier': search_query.get('tier', ''),
                'priority': search_query.get('priority', '')
            }
            
        except Exception:
            return None
    
    def _extract_company_website(self, company_url: str) -> str:
        """Visit company page and extract website"""
        if not company_url:
            return ''
        
        try:
            # Use shared rate limiter
            self.rate_limiter.wait_if_needed()
            
            self.driver.get(company_url)
            time.sleep(random.uniform(2, 4))
            
            # Look for website link
            website_selectors = [
                "a[href^='http']:not([href*='linkedin.com'])",
                ".pv-contact-info__contact-link",
                "[data-test-id='website']",
                ".website-link"
            ]
            
            for selector in website_selectors:
                try:
                    website_elem = self.driver.find_element(By.CSS_SELECTOR, selector)
                    website = website_elem.get_attribute('href')
                    if website and 'linkedin.com' not in website:
                        return website
                except NoSuchElementException:
                    continue
            
            return ''
            
        except Exception:
            return ''
    
    def scrape_linkedin_companies(self, max_searches: int = 10) -> List[Dict]:
        """Main scraping function for LinkedIn companies"""
        
        # Setup WebDriver
        self.driver = self._setup_driver()
        if not self.driver:
            return []
        
        all_leads = []
        
        try:
            # Get queries from bucket manager or provided plan
            queries = self.bucket_manager.get_search_queries()
            targeted_queries = queries[:max_searches]
            
            print(f"Executing {len(targeted_queries)} LinkedIn searches...")
            
            for i, query in enumerate(targeted_queries):
                print(f"\n[{i+1}/{len(targeted_queries)}] Searching: {query['query']}")
                
                leads = self._search_linkedin(query)
                all_leads.extend(leads)
                
                if leads:
                    print(f"  ✓ Found {len(leads)} companies")
                
                # Longer delay between LinkedIn searches
                if i < len(targeted_queries) - 1:
                    time.sleep(random.uniform(10, 20))
            
        except Exception as e:
            print(f"Error during LinkedIn scraping: {e}")
        
        finally:
            if self.driver:
                self.driver.quit()
        
        return all_leads
    
    def _search_linkedin(self, query: Dict) -> List[Dict]:
        """Search LinkedIn for companies"""
        try:
            # Use shared rate limiter
            self.rate_limiter.wait_if_needed()
            
            # Construct search URL
            search_params = {
                'keywords': query['query'],
                'currentCompany': '[""]',
                'geoId': '102713980',  # India
                'resultType': 'COMPANIES'
            }
            
            search_url = f"{self.search_url}?{urlencode(search_params)}"
            self.driver.get(search_url)
            
            # Wait for results to load
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".entity-result"))
            )
            
            # Scroll to load more results
            self._random_scroll(self.driver, scrolls=2)
            
            # Find all company results
            company_elements = self.driver.find_elements(By.CSS_SELECTOR, ".entity-result")
            
            leads = []
            for element in company_elements[:20]:  # Limit per search
                lead = self._extract_company_info(element, query)
                if lead:
                    leads.append(lead)
            
            return leads
            
        except TimeoutException:
            print("    ✗ Timeout waiting for LinkedIn results")
            return []
        except Exception as e:
            print(f"    ✗ Error searching LinkedIn: {e}")
            return []

if __name__ == '__main__':
    # Demo usage
    scraper = LinkedInScraper(headless=True)
    
    print("=== LINKEDIN COMPANY SCRAPER ===")
    print("Note: This requires ChromeDriver to be installed")
    
    # Scrape B2B companies
    leads = scraper.scrape_linkedin_companies(max_searches=5)
    
    if leads:
        print(f"\nFound {len(leads)} total leads")
        
        # Show sample leads
        print("\n=== SAMPLE LEADS ===")
        for lead in leads[:3]:
            print(f"{lead['business_name']} ({lead['category']})")
            print(f"  Location: {lead['city']}")
            print(f"  Website: {lead['website']}")
            print(f"  LinkedIn: {lead['linkedin_url']}")
            print(f"  Quality Score: {lead.get('quality_score', 0):.2f}")
            print()
        
        # Save to database
        scraper.save_to_database(leads)
    else:
        print("No leads found or scraping failed")
# Import for URL encoding
from urllib.parse import urlencode

if __name__ == '__main__':
    # Demo usage
    scraper = LinkedInScraper(headless=True)
    
    print("=== LINKEDIN COMPANY SCRAPER ===")
    print("Note: This requires ChromeDriver to be installed")
    print("Install with: pip install selenium")
    print("Download ChromeDriver: https://chromedriver.chromium.org/")
    
    # Scrape B2B companies
    leads = scraper.scrape_linkedin_companies(max_searches=5)
    
    if leads:
        print(f"\nFound {len(leads)} total leads")
        
        # Show sample leads
        print("\n=== SAMPLE LEADS ===")
        for lead in leads[:3]:
            print(f"{lead['business_name']} ({lead['category']})")
            print(f"  Location: {lead['city']}")
            print(f"  Website: {lead['website']}")
            print(f"  LinkedIn: {lead['linkedin_url']}")
            print(f"  Quality Score: {lead.get('quality_score', 0):.2f}")
            print()
        
        # Save to database
        scraper.save_to_database(leads)
    else:
        print("No leads found or scraping failed")
