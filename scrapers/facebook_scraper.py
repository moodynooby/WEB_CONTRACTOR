"""
Facebook Business Pages Scraper
Uses Graph API and web scraping for business page discovery
"""

import requests
import json
import time
import random
import re
from typing import List, Dict, Optional
from scrapers.base_scraper import BaseScraper

class FacebookScraper(BaseScraper):
    """Facebook Business Pages scraper with API and web fallback"""
    
    def __init__(self, access_token: Optional[str] = None):
        super().__init__('facebook')
        self.access_token = access_token
        
        # API endpoints
        self.graph_api_url = "https://graph.facebook.com/v18.0"
        self.web_search_url = "https://www.facebook.com/search/pages/"
    
    def search_pages_api(self, query: str, limit: int = 50) -> List[Dict]:
        """Search Facebook pages using Graph API"""
        if not self.access_token:
            print("Warning: No Facebook access token provided, using web fallback")
            return self._scrape_web_fallback(query)
        
        params = {
            'q': query,
            'type': 'page',
            'limit': limit,
            'fields': 'name,category,about,phone,website,location,fan_count',
            'access_token': self.access_token
        }
        
        try:
            # Use ethical scraper for rate limiting
            response = self.ethical_scraper.make_request(
                f"{self.graph_api_url}/search", 
                params=params
            )
            
            if not response:
                return []
                
            data = response.json()
            
            if 'error' in data:
                print(f"Facebook API Error: {data['error']['message']}")
                return []
            
            pages = []
            for page_data in data.get('data', []):
                page = self._process_page_data(page_data, query)
                if page:
                    pages.append(page)
            
            return pages
            
        except Exception as e:
            print(f"Facebook API request failed: {e}")
            return []
    
    def _process_page_data(self, page_data: Dict, search_query: str) -> Optional[Dict]:
        """Process and validate Facebook page data"""
        try:
            name = page_data.get('name', '')
            category = page_data.get('category', '')
            about = page_data.get('about', '')
            phone = page_data.get('phone', '')
            website = page_data.get('website', '')
            location = page_data.get('location', {})
            fan_count = page_data.get('fan_count', 0)
            
            # Skip if no website
            if not website:
                return None
            
            # Extract city from location
            city = location.get('city', 'Unknown') if location else 'Unknown'
            
            # Determine business category using BaseScraper's method
            # Combine text fields for better matching
            context_text = f"{search_query} {category} {about} {name}"
            business_category = self.determine_category(context_text, default=category or 'Other')
            
            # Calculate quality score using BaseScraper's wrapper
            quality_score = self.calculate_quality_score({
                'category': business_category,
                'location': city,
                'website': website,
                'phone': phone
            })
            
            # Boost score for pages with good engagement
            if fan_count > 1000:
                quality_score += 0.05
            if fan_count > 5000:
                quality_score += 0.05
            
            return {
                'business_name': name,
                'category': business_category,
                'location': city,
                'phone': phone,
                'website': website,
                'facebook_category': category,
                'about': about,
                'fan_count': fan_count,
                'source': 'facebook_api',
                'quality_score': min(quality_score, 1.0),
                'search_query': search_query
            }
            
        except Exception as e:
            print(f"Error processing Facebook page data: {e}")
            return None
    
    def _scrape_web_fallback(self, query: str) -> List[Dict]:
        """Fallback web scraping when API is not available"""
        print(f"Using web fallback for Facebook search: {query}")
        # This would implement web scraping of Facebook search results
        return []
    
    def scrape_by_buckets(self, max_queries: int = 15) -> List[Dict]:
        """Scrape Facebook pages based on bucket definitions"""
        queries = self.bucket_manager.get_search_queries()
        all_leads = []
        
        # Limit queries for testing
        queries = queries[:max_queries]
        
        print(f"Executing {len(queries)} Facebook searches...")
        
        for i, query in enumerate(queries):
            print(f"\n[{i+1}/{len(queries)}] Searching: {query['query']}")
            
            pages = self.search_pages_api(query['query'], limit=25)
            
            for page in pages:
                # Add bucket information
                page['bucket'] = query.get('bucket', '')
                page['tier'] = query.get('tier', '')
                page['priority'] = query.get('priority', '')
                all_leads.append(page)
            
            if pages:
                print(f"  ✓ Found {len(pages)} Facebook pages")
            
            # Add delay between searches
            if i < len(queries) - 1:
                time.sleep(random.uniform(2, 4))
        
        return all_leads
    
    def get_page_insights(self, page_id: str) -> Dict:
        """Get additional insights for a Facebook page (API required)"""
        if not self.access_token:
            return {}
        
        params = {
            'metric': 'page_impressions,page_engaged_users,page_fan_adds',
            'period': 'week',
            'access_token': self.access_token
        }
        
        try:
            response = self.ethical_scraper.make_request(
                f"{self.graph_api_url}/{page_id}/insights",
                params=params
            )
            return response.json() if response else {}
        except Exception as e:
            print(f"Error getting page insights: {e}")
            return {}

if __name__ == '__main__':
    # Demo usage
    scraper = FacebookScraper()  # Add access token as parameter if available
    
    print("=== FACEBOOK BUSINESS PAGES SCRAPER ===")
    print("Note: For best results, provide a Facebook Graph API access token")
    print("Get token from: https://developers.facebook.com/")
    
    # Scrape Facebook pages
    leads = scraper.scrape_by_buckets(max_queries=10)
    
    if leads:
        print(f"\nFound {len(leads)} total leads")
        
        # Show sample leads
        print("\n=== SAMPLE LEADS ===")
        for lead in leads[:5]:
            print(f"{lead['business_name']} ({lead['category']})")
            print(f"  Location: {lead['location']}")
            print(f"  Website: {lead['website']}")
            print(f"  Facebook Category: {lead.get('facebook_category', 'N/A')}")
            print(f"  Fans: {lead.get('fan_count', 0):,}")
            print(f"  Quality Score: {lead.get('quality_score', 0):.2f}")
            print()
        
        # Save to database
        scraper.save_to_database(leads)
    else:
        print("No leads found. Consider adding Facebook API access token for better results.")
