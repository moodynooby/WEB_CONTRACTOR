import sqlite3
import time
import random
import re
from typing import List, Dict, Optional, Union
from core.lead_buckets import LeadBucketManager
from core.rate_limiter import get_scraper

class BaseScraper:
    """
    Base class for all scrapers, providing common utilities for:
    - Database operations
    - Rate limiting
    - City extraction
    - Category determination
    - User agent rotation
    """
    
    # Common Indian cities for extraction
    INDIAN_CITIES = [
        'Mumbai', 'Delhi', 'Bangalore', 'Bengaluru', 'Chennai', 'Kolkata', 'Hyderabad', 'Pune',
        'Ahmedabad', 'Jaipur', 'Lucknow', 'Indore', 'Surat', 'Nagpur', 'Bhopal',
        'Vadodara', 'Rajkot', 'Gandhinagar', 'Chandigarh', 'Coimbatore', 'Kochi',
        'Visakhapatnam', 'Thiruvananthapuram', 'Noida', 'Gurgaon', 'Gurugram'
    ]

    # Common category keywords mapping
    CATEGORY_KEYWORDS = {
        'Interior Designer': ['interior design', 'interior designer', 'home decor', 'furniture', 'decor'],
        'Architect': ['architect', 'architecture', 'building design', 'planner'],
        'Plumber': ['plumber', 'plumbing', 'pipe repair', 'sanitary'],
        'Electrician': ['electrician', 'electrical', 'wiring', 'power'],
        'HVAC Service': ['hvac', 'air conditioning', 'ac repair', 'heating', 'cooling'],
        'Pest Control': ['pest control', 'exterminator', 'termite', 'fumigation'],
        'Cleaning Service': ['cleaning', 'house keeping', 'deep cleaning', 'sanitization'],
        'Event Management': ['event', 'wedding', 'party planner', 'corporate event', 'conference'],
        'Photography Studio': ['photography', 'photo studio', 'photographer', 'wedding photo'],
        'Marketing Consultant': ['marketing', 'digital marketing', 'advertising', 'branding', 'seo'],
        'Graphics Designer': ['graphic', 'logo design', 'illustrator', 'visual design', 'creative'],
        'Accountant': ['accountant', 'ca', 'chartered accountant', 'audit', 'taxation', 'bookkeeping'],
        'Tax Consultant': ['tax consultant', 'gst', 'income tax', 'tax return'],
        'Legal Services': ['lawyer', 'advocate', 'attorney', 'legal', 'law firm', 'notary'],
        'IT Services': ['software', 'web development', 'app development', 'it solution', 'tech'],
    }

    def __init__(self, source_name: str):
        self.source_name = source_name
        self.bucket_manager = LeadBucketManager()
        # Use centralized rate limiter
        self.ethical_scraper = get_scraper(source_name)
        self.session = self.ethical_scraper.session
        # Expose rate_limiter directly for non-HTTP scrapers (like Selenium)
        self.rate_limiter = self.ethical_scraper.rate_limiter

    def _rate_limit(self) -> None:
        """Enforce rate limits using the centralized limiter"""
        self.rate_limiter.wait_if_needed()

    def save_to_database(self, leads: List[Dict], source: Optional[str] = None) -> int:
        """
        Common method to save leads to database.
        Handles duplicates and connection management.
        """
        if not leads:
            return 0
            
        conn = sqlite3.connect('leads.db')
        cursor = conn.cursor()
        
        saved_count = 0
        current_source = source or self.source_name
        
        for lead in leads:
            try:
                # Ensure all fields exist
                business_name = lead.get('business_name', '')
                if not business_name:
                    continue
                    
                cursor.execute('''
                INSERT OR REPLACE INTO leads 
                (business_name, category, location, phone, website, source, status, quality_score, bucket)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    business_name,
                    lead.get('category', 'Unknown'),
                    lead.get('location', '') or lead.get('city', ''),
                    lead.get('phone', ''),
                    lead.get('website', ''),
                    lead.get('source', current_source),
                    'pending_audit',
                    lead.get('quality_score', 0.5),
                    lead.get('bucket', '')
                ))
                saved_count += 1
            except sqlite3.IntegrityError:
                # Duplicate business name, skip
                # (In a real app, we might want to update fields instead of skipping)
                continue
            except Exception as e:
                print(f"Error saving lead {lead.get('business_name')}: {e}")
        
        conn.commit()
        conn.close()
        
        print(f"\n✓ Saved {saved_count} new leads to database from {current_source}")
        return saved_count

    def extract_city(self, text: str) -> str:
        """Extract Indian city from text (address/location)"""
        if not text:
            return 'Unknown'
            
        text_lower = text.lower()
        for city in self.INDIAN_CITIES:
            if city.lower() in text_lower:
                return city
        
        # Fallback: try to extract from last part of comma-separated string
        parts = text.split(',')
        if len(parts) >= 2:
            return parts[-2].strip()
            
        return 'Unknown'

    def determine_category(self, text: str, default: str = 'Other') -> str:
        """Determine category based on keywords in text"""
        text_lower = text.lower()
        
        for category, keywords in self.CATEGORY_KEYWORDS.items():
            for keyword in keywords:
                if keyword in text_lower:
                    return category
                    
        return default

    def calculate_quality_score(self, lead_data: Dict) -> float:
        """Wrapper around bucket_manager's quality score"""
        return self.bucket_manager.calculate_lead_quality_score(lead_data)

