from typing import List, Dict, Optional, Union
from core.lead_buckets import LeadBucketManager
from core.rate_limiter import get_scraper

class BaseScraper:
    """
    Base class for all scrapers, providing common utilities for:
    - Database operations
    - Rate limiting (via core.rate_limiter)
    - Quality scoring
    """
    
    def __init__(self, source_name: str):
        self.source_name = source_name
        self.bucket_manager = LeadBucketManager()
        # Use centralized rate limiter
        self.ethical_scraper = get_scraper(source_name)
        self.session = self.ethical_scraper.session
        # Expose rate_limiter directly for non-HTTP scrapers (like Selenium)
        self.rate_limiter = self.ethical_scraper.rate_limiter

    def save_to_database(self, leads: List[Dict], source: Optional[str] = None) -> int:
        """
        Common method to save leads to database.
        Handles duplicates and connection management.
        """
        if not leads:
            return 0
            
        print(f"Saving {len(leads)} leads to database...")
        from core.db import LeadRepository
        
        repo = LeadRepository()
        saved_count = repo.add_leads_bulk(leads)
            
        print(f"\n✓ Saved {saved_count} new leads to database from {source or self.source_name}")
        
        # Log this scraping session
        from core.db import log_scraping_session
        log_scraping_session(
            source=source or self.source_name, 
            query=f"Batch save {len(leads)} leads", 
            leads_found=len(leads), 
            leads_saved=saved_count
        )
            
        return saved_count

    def calculate_quality_score(self, lead_data: Dict) -> float:
        """Wrapper around bucket_manager's quality score"""
        return self.bucket_manager.calculate_lead_quality_score(lead_data)

    def extract_city_from_text(self, text: str, target_city: Optional[str] = None) -> str:
        """
        Extract city from text. If target_city is provided, checks for it.
        Otherwise uses a general extraction logic.
        """
        if not text:
            return target_city or 'Unknown'
            
        if target_city and target_city.lower() in text.lower():
            return target_city
            
        # Fallback to simple comma parsing
        parts = text.split(',')
        if len(parts) >= 2:
            return parts[-2].strip()
            
        return target_city or 'Unknown'

    def determine_category(self, text: str, default: str = 'Other') -> str:
        """
        Dynamically determine category based on LeadBucketManager definitions.
        """
        if not text:
            return default
            
        text = text.lower()
        
        # Check all buckets and their categories
        for bucket in self.bucket_manager.buckets:
            for category in bucket.categories:
                if category.lower() in text:
                    return category
            
            # Also check bucket name keywords
            if bucket.name.lower() in text:
                return bucket.categories[0]
                
        return default

