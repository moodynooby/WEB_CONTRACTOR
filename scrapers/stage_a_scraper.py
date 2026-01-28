"""
Stage A: Intelligent Scraper Execution
Executes the discovery plan across multiple sources with rate limiting
"""

import time
import random
from typing import List, Dict, Optional
from dataclasses import dataclass
import sqlite3
import json

# Import existing scrapers
from scrapers.google_maps_scraper import GoogleMapsScraper
from scrapers.yellow_pages_scraper import YellowPagesScraper
from scrapers.linkedin_scraper import LinkedInScraper
from scrapers.facebook_scraper import FacebookScraper
from core.rate_limiter import get_scraper
from core.lead_buckets import LeadBucketManager
from core.db import log_scraping_session

@dataclass
class ScrapingSession:
    """Tracks a scraping session metrics"""
    source: str
    start_time: float
    leads_found: int = 0
    leads_saved: int = 0
    errors: List[str] = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []

class StageAScraper:
    """Stage A: Intelligent Scraper Orchestrator"""
    
    def __init__(self):
        self.bucket_manager = LeadBucketManager()
        
        # Initialize individual scrapers
        self.google_scraper = GoogleMapsScraper()
        self.linkedin_scraper = LinkedInScraper()
        self.facebook_scraper = FacebookScraper()
        # Yellow Pages is skipped for now, but we keep the instance if needed later
        self.yellow_pages_scraper = YellowPagesScraper()
        
    def scrape_source(self, source: str, max_queries: int = 50, plan: List[Dict] = None) -> Dict:
        """Execute scraping for a specific source"""
        print(f"\n=== STAGE A: EXECUTING {source.upper()} ===")
        
        session = ScrapingSession(source=source, start_time=time.time())
        leads = []
        
        try:
            if source == 'google_maps':
                leads = self.google_scraper.scrape_by_buckets(max_queries_per_bucket=5)
            elif source == 'linkedin':
                leads = self.linkedin_scraper.scrape_linkedin_companies(max_searches=max_queries)
            elif source == 'facebook':
                leads = self.facebook_scraper.scrape_by_buckets(max_queries=max_queries)
            elif source == 'yellow_pages':
                print("Skipping Yellow Pages as requested...")
                leads = []
            else:
                raise ValueError(f"Unknown source: {source}")
            
            # Save leads (individual scrapers handle their own saving, but we can aggregate)
            session.leads_found = len(leads)
            # Individual scrapers already saved to DB in their main methods, 
            # but we can call save_to_database again if we want to be sure or log it.
            # For now, we rely on the scraper's internal saving.
            session.leads_saved = len(leads) # Simplified
            
        except Exception as e:
            error_msg = f"Scraping {source} failed: {str(e)}"
            session.errors.append(error_msg)
            print(f"✗ {error_msg}")
        
        results = {
            'source': source,
            'leads_found': session.leads_found,
            'leads_saved': session.leads_saved,
            'duration': time.time() - session.start_time,
            'errors': session.errors
        }
        
        # Log session results
        log_scraping_session(
            source=source,
            query=f"Stage A scraping session",
            leads_found=session.leads_found,
            leads_saved=session.leads_saved,
            error_message=', '.join(session.errors) if session.errors else None
        )
        
        return results

    def run_all_sources(self, max_queries_per_source: int = 20, plan: List[Dict] = None) -> Dict:
        """Run all active scraping sources"""
        print("=== STAGE A: EXECUTION - SCRAPING DISCOVERIES ===")
        
        sources = ['google_maps', 'linkedin', 'facebook']
        all_results = {
            'total_leads_found': 0,
            'total_leads_saved': 0,
            'source_results': {},
            'total_duration': 0
        }
        
        start_time = time.time()
        
        for source in sources:
            result = self.scrape_source(source, max_queries_per_source, plan=plan)
            all_results['source_results'][source] = result
            all_results['total_leads_found'] += result['leads_found']
            all_results['total_leads_saved'] += result['leads_saved']
            
            # Short delay between sources
            if source != sources[-1]:
                time.sleep(5)
        
        all_results['total_duration'] = time.time() - start_time
        self._print_final_summary(all_results)
        return all_results
    
    def _print_final_summary(self, results: Dict):
        """Print final summary for all sources"""
        print(f"\n{'='*60}")
        print("STAGE A: INTELLIGENT SCRAPER - FINAL SUMMARY")
        print(f"{'='*60}")
        print(f"Total Duration: {results['total_duration']:.1f}s")
        print(f"Total Leads Found: {results['total_leads_found']}")
        print(f"Total Leads Saved: {results['total_leads_saved']}")
        
        print(f"\n--- Results by Source ---")
        for source, result in results['source_results'].items():
            print(f"{source.replace('_', ' ').title()}: Found {result['leads_found']}, Saved {result['leads_saved']}")

if __name__ == '__main__':
    scraper = StageAScraper()
    print("Stage A: Intelligent Scraper Orchestrator")
    results = scraper.run_all_sources(max_queries_per_source=5)
