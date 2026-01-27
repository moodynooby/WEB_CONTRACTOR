"""
Stage 0 Orchestrator: Lead Discovery & Bucket Definition
Coordinates all scraping activities and manages the lead discovery pipeline
"""

import time
import json
from datetime import datetime, timedelta
from typing import List, Dict
import sqlite3

from core.lead_buckets import LeadBucketManager
from scrapers.google_maps_scraper import GoogleMapsScraper
from scrapers.yellow_pages_scraper import YellowPagesScraper
from scrapers.linkedin_scraper import LinkedInScraper
from scrapers.facebook_scraper import FacebookScraper
from core.db import init_database, populate_buckets, log_scraping_session, record_analytic, get_database_stats
from core.rate_limiter import get_scraper

class Stage0Orchestrator:
    """Orchestrates Stage 0 lead discovery across all sources"""
    
    def __init__(self):
        self.bucket_manager = LeadBucketManager()
        
        # Initialize scrapers
        self.google_scraper = GoogleMapsScraper()
        self.yellow_pages_scraper = YellowPagesScraper()
        self.linkedin_scraper = LinkedInScraper()
        self.facebook_scraper = FacebookScraper()
        
        # Initialize database
        init_database()
        populate_buckets()
        
        # Scraping schedule
        self.scraping_schedule = {
            'google_maps': {'enabled': True, 'priority': 1, 'max_queries': 50},
            'yellow_pages': {'enabled': True, 'priority': 2, 'max_queries': 100},
            'linkedin': {'enabled': True, 'priority': 3, 'max_queries': 30},
            'facebook': {'enabled': True, 'priority': 4, 'max_queries': 40}
        }
    
    def run_full_discovery(self, daily_mode: bool = True) -> Dict:
        """Run complete lead discovery pipeline"""
        print("=== STAGE 0: LEAD DISCOVERY & BUCKET DEFINITION ===")
        print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        results = {
            'total_leads_found': 0,
            'total_leads_saved': 0,
            'source_results': {},
            'errors': [],
            'duration': 0
        }
        
        start_time = time.time()
        
        # Get enabled scrapers sorted by priority
        enabled_sources = [
            (source, config) for source, config in self.scraping_schedule.items() 
            if config['enabled']
        ]
        enabled_sources.sort(key=lambda x: x[1]['priority'])
        
        for source, config in enabled_sources:
            print(f"\n--- Scraping {source.replace('_', ' ').title()} ---")
            
            try:
                source_results = self._scrape_source(source, config, daily_mode)
                results['source_results'][source] = source_results
                results['total_leads_found'] += source_results['leads_found']
                results['total_leads_saved'] += source_results['leads_saved']
                
                # Log session
                log_scraping_session(
                    source=source,
                    query=f"Batch discovery - {source}",
                    leads_found=source_results['leads_found'],
                    leads_saved=source_results['leads_saved']
                )
                
                print(f"✓ {source}: {source_results['leads_saved']} leads saved")
                
                # Add delay between sources
                if source != enabled_sources[-1][0]:
                    time.sleep(30)  # 30 second delay between sources
                
            except Exception as e:
                error_msg = f"Error scraping {source}: {str(e)}"
                results['errors'].append(error_msg)
                print(f"✗ {error_msg}")
                
                # Log error
                log_scraping_session(
                    source=source,
                    query=f"Batch discovery - {source}",
                    leads_found=0,
                    leads_saved=0,
                    error_message=error_msg
                )
        
        # Calculate duration
        results['duration'] = time.time() - start_time
        
        # Record analytics
        self._record_discovery_analytics(results)
        
        # Show summary
        self._print_summary(results)
        
        return results
    
    def _scrape_source(self, source: str, config: Dict, daily_mode: bool) -> Dict:
        """Scrape a specific source"""
        max_queries = config['max_queries'] if daily_mode else config['max_queries'] // 2
        
        if source == 'google_maps':
            leads = self.google_scraper.scrape_by_buckets(max_queries_per_bucket=max_queries // 4)
            saved = self.google_scraper.save_to_database(leads)
            
        elif source == 'yellow_pages':
            leads = self.yellow_pages_scraper.scrape_yellow_directory(max_queries=max_queries)
            saved = self.yellow_pages_scraper.save_to_database(leads)
            
        elif source == 'linkedin':
            leads = self.linkedin_scraper.scrape_linkedin_companies(max_searches=max_queries)
            saved = self.linkedin_scraper.save_to_database(leads)
            
        elif source == 'facebook':
            leads = self.facebook_scraper.scrape_by_buckets(max_queries=max_queries)
            saved = self.facebook_scraper.save_to_database(leads)
            
        else:
            leads = []
            saved = 0
        
        return {
            'leads_found': len(leads),
            'leads_saved': saved,
            'quality_avg': sum(lead.get('quality_score', 0.5) for lead in leads) / len(leads) if leads else 0
        }
    
    def _record_discovery_analytics(self, results: Dict):
        """Record discovery session analytics"""
        # Overall metrics
        record_analytic(
            metric_name='total_leads_discovered',
            metric_value=results['total_leads_found'],
            notes=f"Discovery session completed in {results['duration']:.1f}s"
        )
        
        record_analytic(
            metric_name='total_leads_saved',
            metric_value=results['total_leads_saved'],
            notes=f"Discovery session completed in {results['duration']:.1f}s"
        )
        
        record_analytic(
            metric_name='discovery_success_rate',
            metric_value=results['total_leads_saved'] / max(results['total_leads_found'], 1),
            notes=f"Success rate: {results['total_leads_saved']}/{results['total_leads_found']}"
        )
        
        # Source-specific metrics
        for source, source_results in results['source_results'].items():
            record_analytic(
                metric_name='leads_discovered',
                metric_value=source_results['leads_found'],
                source=source,
                notes=f"Quality avg: {source_results['quality_avg']:.2f}"
            )
            
            record_analytic(
                metric_name='leads_saved',
                metric_value=source_results['leads_saved'],
                source=source
            )
    
    def _print_summary(self, results: Dict):
        """Print discovery session summary"""
        print(f"\n{'='*50}")
        print("DISCOVERY SESSION SUMMARY")
        print(f"{'='*50}")
        print(f"Duration: {results['duration']:.1f} seconds")
        print(f"Total Leads Found: {results['total_leads_found']}")
        print(f"Total Leads Saved: {results['total_leads_saved']}")
        print(f"Success Rate: {results['total_leads_saved']/max(results['total_leads_found'], 1):.1%}")
        
        if results['source_results']:
            print(f"\n--- Results by Source ---")
            for source, source_results in results['source_results'].items():
                print(f"{source.replace('_', ' ').title()}:")
                print(f"  Found: {source_results['leads_found']}")
                print(f"  Saved: {source_results['leads_saved']}")
                print(f"  Quality Avg: {source_results['quality_avg']:.2f}")
        
        if results['errors']:
            print(f"\n--- Errors ---")
            for error in results['errors']:
                print(f"✗ {error}")
        
        # Show database stats
        print(f"\n--- Database Statistics ---")
        stats = get_database_stats()
        
        if 'leads_by_status' in stats:
            print(f"Leads by Status: {stats['leads_by_status']}")
        
        if 'leads_by_source' in stats:
            print(f"Leads by Source: {stats['leads_by_source']}")
        
        if 'leads_by_bucket' in stats:
            print(f"Leads by Bucket: {stats['leads_by_bucket']}")
    
    def get_monthly_progress(self) -> Dict:
        """Get monthly lead discovery progress"""
        conn = sqlite3.connect('leads.db')
        cursor = conn.cursor()
        
        # Get current month leads
        current_month = datetime.now().strftime('%Y-%m')
        cursor.execute('''
        SELECT source, COUNT(*) as count
        FROM leads 
        WHERE created_at LIKE ?
        GROUP BY source
        ''', (f"{current_month}%",))
        
        monthly_by_source = dict(cursor.fetchall())
        
        # Get monthly targets
        targets = self.bucket_manager.get_monthly_targets()
        total_target = sum(targets.values())
        
        # Get current month total
        cursor.execute('''
        SELECT COUNT(*) FROM leads 
        WHERE created_at LIKE ?
        ''', (f"{current_month}%",))
        
        monthly_total = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            'current_month': current_month,
            'monthly_total': monthly_total,
            'monthly_target': total_target,
            'progress_percentage': monthly_total / max(total_target, 1),
            'by_source': monthly_by_source,
            'targets_by_bucket': targets
        }
    
    def run_targeted_scraping(self, bucket_name: str, max_queries: int = 20) -> Dict:
        """Run scraping for a specific bucket"""
        print(f"=== TARGETED SCRAPING: {bucket_name} ===")
        
        results = {
            'bucket': bucket_name,
            'total_leads_found': 0,
            'total_leads_saved': 0,
            'source_results': {}
        }
        
        # Get queries for specific bucket
        queries = self.bucket_manager.get_search_queries(bucket_name)
        queries = queries[:max_queries]
        
        # Run scrapers with bucket-specific queries
        for source, config in self.scraping_schedule.items():
            if not config['enabled']:
                continue
            
            print(f"\n--- Scraping {source.replace('_', ' ').title()} for {bucket_name} ---")
            
            try:
                if source == 'google_maps':
                    leads = self.google_scraper.scrape_by_buckets(max_queries_per_bucket=len(queries) // 4)
                    saved = self.google_scraper.save_to_database(leads)
                elif source == 'yellow_pages':
                    leads = self.yellow_pages_scraper.scrape_yellow_directory(max_queries=len(queries))
                    saved = self.yellow_pages_scraper.save_to_database(leads)
                elif source == 'linkedin':
                    leads = self.linkedin_scraper.scrape_linkedin_companies(max_searches=len(queries))
                    saved = self.linkedin_scraper.save_to_database(leads)
                elif source == 'facebook':
                    leads = self.facebook_scraper.scrape_by_buckets(max_queries=len(queries))
                    saved = self.facebook_scraper.save_to_database(leads)
                else:
                    leads = []
                    saved = 0
                
                results['source_results'][source] = {
                    'leads_found': len(leads),
                    'leads_saved': saved
                }
                results['total_leads_found'] += len(leads)
                results['total_leads_saved'] += saved
                
                print(f"✓ {source}: {saved} leads saved")
                
            except Exception as e:
                print(f"✗ Error scraping {source}: {e}")
        
        print(f"\n--- {bucket_name} Summary ---")
        print(f"Total Leads Found: {results['total_leads_found']}")
        print(f"Total Leads Saved: {results['total_leads_saved']}")
        
        return results

if __name__ == '__main__':
    # Demo usage
    orchestrator = Stage0Orchestrator()
    
    print("Choose an option:")
    print("1. Run full discovery (daily mode)")
    print("2. Run full discovery (test mode)")
    print("3. Run targeted scraping for a bucket")
    print("4. Show monthly progress")
    
    choice = input("Enter choice (1-4): ").strip()
    
    if choice == '1':
        results = orchestrator.run_full_discovery(daily_mode=True)
    elif choice == '2':
        results = orchestrator.run_full_discovery(daily_mode=False)
    elif choice == '3':
        buckets = [bucket.name for bucket in orchestrator.bucket_manager.buckets]
        print(f"Available buckets: {', '.join(buckets)}")
        bucket = input("Enter bucket name: ").strip()
        if bucket in buckets:
            results = orchestrator.run_targeted_scraping(bucket)
        else:
            print("Invalid bucket name")
    elif choice == '4':
        progress = orchestrator.get_monthly_progress()
        print(f"\n=== MONTHLY PROGRESS ===")
        print(f"Month: {progress['current_month']}")
        print(f"Progress: {progress['monthly_total']}/{progress['monthly_target']} ({progress['progress_percentage']:.1%})")
        print(f"By Source: {progress['by_source']}")
        print(f"Targets by Bucket: {progress['targets_by_bucket']}")
    else:
        print("Invalid choice")
