"""
Google Maps API Scraper for High-Quality Lead Generation
Respects rate limits and robots.txt for ethical scraping
"""

import requests
import time
import random
import json
from typing import List, Dict, Optional
from scrapers.base_scraper import BaseScraper

class GoogleMapsScraper(BaseScraper):
    """Google Maps scraper with API integration and rate limiting"""
    
    def __init__(self, api_key: Optional[str] = None):
        super().__init__('google_maps')
        self.api_key = api_key
        self.base_url = "https://maps.googleapis.com/maps/api"
        
    def search_places_api(self, query: str, location: str = None, radius: int = 5000) -> List[Dict]:
        """Search for places using Google Places API"""
        if not self.api_key:
            print("Warning: No Google Maps API key provided, falling back to web scraping")
            return self._scrape_web_fallback(query)
        
        params = {
            'query': query,
            'key': self.api_key,
            'fields': 'place_id,name,formatted_address,formatted_phone_number,website,rating,types'
        }
        
        if location:
            params['locationbias'] = location
            params['radius'] = radius
        
        try:
            # Use ethical scraper for rate limiting
            response = self.ethical_scraper.make_request(
                f"{self.base_url}/place/textsearch/json", 
                params=params
            )
            
            if not response:
                return []
                
            data = response.json()
            
            if data.get('status') == 'OK':
                places = []
                for place in data.get('results', []):
                    processed_place = self._process_place_data(place, query)
                    if processed_place:
                        places.append(processed_place)
                
                return places
            else:
                print(f"API Error: {data.get('status')} - {data.get('error_message', '')}")
                return []
                
        except Exception as e:
            print(f"API request failed: {e}")
            return []
    
    def _process_place_data(self, place: Dict, search_query: str) -> Optional[Dict]:
        """Process and validate place data"""
        try:
            # Extract relevant information
            website = place.get('website', '')
            
            # Skip if no website (primary requirement)
            if not website:
                return None
            
            name = place.get('name', '')
            address = place.get('formatted_address', '')
            phone = place.get('formatted_phone_number', '')
            rating = place.get('rating', 0)
            place_id = place.get('place_id', '')
            types = place.get('types', [])
            
            # Extract city from address using BaseScraper
            city = self.extract_city(address)
            
            # Determine category from search query and place types using BaseScraper
            # Combine types into a string for keyword matching
            types_str = ' '.join(types)
            category = self.determine_category(f"{search_query} {types_str}", default='Local Service Provider')
            
            # Calculate quality score
            quality_score = self.calculate_quality_score({
                'category': category,
                'location': city,
                'website': website,
                'phone': phone
            })
            
            return {
                'business_name': name,
                'address': address,
                'city': city,
                'phone': phone,
                'website': website,
                'category': category,
                'rating': rating,
                'place_id': place_id,
                'source': 'google_maps_api',
                'quality_score': quality_score,
                'search_query': search_query,
                'types': types
            }
            
        except Exception as e:
            print(f"Error processing place data: {e}")
            return None
    
    def _scrape_web_fallback(self, query: str) -> List[Dict]:
        """Fallback web scraping when API is not available"""
        print(f"Using web fallback for: {query}")
        return []
    
    def scrape_by_buckets(self, max_queries_per_bucket: int = 10) -> List[Dict]:
        """Scrape leads based on bucket definitions"""
        all_leads = []
        
        queries = self.bucket_manager.get_search_queries()
        
        # Limit queries per bucket for testing
        bucket_query_counts = {}
        filtered_queries = []
        
        for query in queries:
            bucket = query['bucket']
            if bucket not in bucket_query_counts:
                bucket_query_counts[bucket] = 0
            
            if bucket_query_counts[bucket] < max_queries_per_bucket:
                filtered_queries.append(query)
                bucket_query_counts[bucket] += 1
        
        print(f"Executing {len(filtered_queries)} search queries...")
        
        for i, query in enumerate(filtered_queries):
            print(f"\n[{i+1}/{len(filtered_queries)}] Searching: {query['query']}")
            
            # Use geographic coordinates for better results
            city_coords = self._get_city_coordinates(query['city'])
            location_bias = f"{city_coords['lat']},{city_coords['lng']}" if city_coords else None
            
            places = self.search_places_api(
                query=query['query'],
                location=location_bias,
                radius=10000  # 10km radius
            )
            
            for place in places:
                # Add bucket information
                place['bucket'] = query.get('bucket', '')
                place['tier'] = query.get('tier', '')
                place['priority'] = query.get('priority', '')
                all_leads.append(place)
            
            print(f"  Found {len(places)} places")
            
            # Additional delay between different queries
            if i < len(filtered_queries) - 1:
                time.sleep(random.uniform(2, 4))
        
        return all_leads
    
    def _get_city_coordinates(self, city: str) -> Dict:
        """Get approximate coordinates for Indian cities"""
        city_coordinates = {
            'Mumbai': {'lat': 19.0760, 'lng': 72.8777},
            'Delhi': {'lat': 28.7041, 'lng': 77.1025},
            'Bangalore': {'lat': 12.9716, 'lng': 77.5946},
            'Chennai': {'lat': 13.0827, 'lng': 80.2707},
            'Kolkata': {'lat': 22.5726, 'lng': 88.3639},
            'Hyderabad': {'lat': 17.3850, 'lng': 78.4867},
            'Pune': {'lat': 18.5204, 'lng': 73.8567},
            'Ahmedabad': {'lat': 23.0225, 'lng': 72.5714},
            'Jaipur': {'lat': 26.9124, 'lng': 75.7873},
            'Lucknow': {'lat': 26.8467, 'lng': 80.9462},
            'Indore': {'lat': 22.7196, 'lng': 75.8577},
            'Surat': {'lat': 21.1702, 'lng': 72.8311},
            'Nagpur': {'lat': 21.1458, 'lng': 79.0882},
            'Bhopal': {'lat': 23.2599, 'lng': 77.4126},
            'Vadodara': {'lat': 22.3072, 'lng': 73.1812},
            'Rajkot': {'lat': 22.3039, 'lng': 70.8022},
            'Gandhinagar': {'lat': 23.2156, 'lng': 72.6369}
        }
        
        return city_coordinates.get(city, {})

if __name__ == '__main__':
    # Demo usage
    scraper = GoogleMapsScraper()  # Add API key as parameter if available
    
    print("=== GOOGLE MAPS LEAD SCRAPER ===")
    
    # Scrape a few queries for testing
    leads = scraper.scrape_by_buckets(max_queries_per_bucket=2)
    
    if leads:
        print(f"\nFound {len(leads)} total leads")
        
        # Show sample leads
        print("\n=== SAMPLE LEADS ===")
        for lead in leads[:5]:
            print(f"{lead['business_name']} ({lead['category']})")
            print(f"  Location: {lead['city']}")
            print(f"  Website: {lead['website']}")
            print(f"  Quality Score: {lead.get('quality_score', 0):.2f}")
            print()
        
        # Save to database
        scraper.save_to_database(leads)
    else:
        print("No leads found. Consider adding Google Maps API key for better results.")
