import requests
from bs4 import BeautifulSoup
import time
import random
import re
from typing import List, Dict
from scrapers.base_scraper import BaseScraper

class YellowPagesScraper(BaseScraper):
    """Enhanced Yellow Pages and local directory scraper with bucket integration"""
    
    def __init__(self):
        super().__init__('yellow_pages')
        
        # Indian business directories
        self.directories = {
            'yellow_co': {
                'base_url': 'https://yellow.co.in',
                'search_path': '/search',
                'enabled': True
            },
            'justdial': {
                'base_url': 'https://www.justdial.com',
                'search_path': '/search',
                'enabled': False  # Requires more complex handling
            },
            'sulekha': {
                'base_url': 'https://www.sulekha.com',
                'search_path': '/search',
                'enabled': False  # Requires more complex handling
            }
        }
    
    def scrape_yellow_directory(self, max_queries: int = 20) -> List[Dict]:
        """Enhanced scraper with bucket-based targeting"""
        
        queries = self.bucket_manager.get_search_queries()
        all_leads = []
        
        # Limit queries for testing
        queries = queries[:max_queries]
        
        for i, query in enumerate(queries):
            print(f"\n[{i+1}/{len(queries)}] Searching: {query['query']}")
            
            # Try different directories
            for dir_name, dir_config in self.directories.items():
                if not dir_config['enabled']:
                    continue
                    
                leads = self._scrape_directory(dir_name, query)
                all_leads.extend(leads)
                
                if leads:
                    print(f"  ✓ Found {len(leads)} leads from {dir_name}")
                
                # Add delay between directories
                if dir_name != list(self.directories.keys())[-1]:
                    time.sleep(random.uniform(3, 6))
            
            # Add delay between queries
            if i < len(queries) - 1:
                time.sleep(random.uniform(5, 8))
        
        return all_leads
    
    def _scrape_directory(self, directory: str, query: Dict) -> List[Dict]:
        """Scrape a specific directory"""
        
        if directory == 'yellow_co':
            return self._scrape_yellow_co(query)
        elif directory == 'justdial':
            return self._scrape_justdial(query)
        elif directory == 'sulekha':
            return self._scrape_sulekha(query)
        
        return []
    
    def _scrape_yellow_co(self, query: Dict) -> List[Dict]:
        """Scrape yellow.co.in"""
        search_term = query['query'].replace(' ', '+')
        url = f"https://yellow.co.in/search/{search_term}"
        
        try:
            # Use ethical_scraper.make_request which handles rate limiting and robots.txt
            response = self.ethical_scraper.make_request(url, timeout=10)
            
            if not response:
                return []
            
            soup = BeautifulSoup(response.content, 'html.parser')
            leads = []
            
            # Look for listing containers
            listings = soup.find_all('div', class_=re.compile(r'listing|result|business'))
            
            for listing in listings[:50]:  # Limit per search
                try:
                    lead = self._parse_yellow_co_listing(listing, query)
                    if lead:
                        leads.append(lead)
                except Exception:
                    continue
            
            return leads
            
        except Exception as e:
            print(f"    ✗ Error scraping yellow.co.in: {e}")
            return []
    
    def _parse_yellow_co_listing(self, listing, query: Dict) -> Dict:
        """Parse individual listing from yellow.co.in"""
        
        # Extract website first (primary requirement)
        website_elem = listing.find('a', href=re.compile(r'http'))
        website = website_elem.get('href') if website_elem else ''
        
        if not website:
            return None
        
        # Extract business name
        name_elem = listing.find(['h2', 'h3', 'h4'], class_=re.compile(r'name|title|business'))
        name = name_elem.text.strip() if name_elem else ''
        
        # Extract phone
        phone_elem = listing.find(['span', 'div'], class_=re.compile(r'phone|mobile|contact'))
        phone = phone_elem.text.strip() if phone_elem else ''
        if phone:
            phone = re.sub(r'[^\d+]', '', phone)
        
        # Calculate quality score
        quality_score = self.calculate_quality_score({
            'category': query['category'],
            'location': query['city'],
            'website': website,
            'phone': phone
        })
        
        return {
            'business_name': name,
            'phone': phone,
            'website': website,
            'location': query['city'],
            'category': query['category'],
            'source': 'yellow_co',
            'quality_score': quality_score,
            'bucket': query.get('bucket', ''),
            'tier': query.get('tier', ''),
            'priority': query.get('priority', '')
        }
    
    def _scrape_justdial(self, query: Dict) -> List[Dict]:
        """Placeholder for JustDial scraping"""
        return []
    
    def _scrape_sulekha(self, query: Dict) -> List[Dict]:
        """Placeholder for Sulekha scraping"""
        return []

# Legacy function for backward compatibility
def scrape_yellow_directory():
    """Legacy function - use YellowPagesScraper class instead"""
    scraper = YellowPagesScraper()
    leads = scraper.scrape_yellow_directory(max_queries=10)
    scraper.save_to_database(leads)

# Legacy function for backward compatibility
def add_to_db(leads):
    """Legacy function - use YellowPagesScraper.save_to_database instead"""
    scraper = YellowPagesScraper()
    scraper.save_to_database(leads)

if __name__ == '__main__':
    # Enhanced usage
    scraper = YellowPagesScraper()
    
    print("=== YELLOW PAGES LEAD SCRAPER ===")
    
    # Scrape leads based on bucket definitions
    leads = scraper.scrape_yellow_directory(max_queries=15)
    
    if leads:
        print(f"\nFound {len(leads)} total leads")
        scraper.save_to_database(leads)
    else:
        print("No leads found")
