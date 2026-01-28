"""
Stage A: Intelligent Scraper with Anti-Blocking
Integrates all scraping sources with advanced anti-blocking mechanisms
"""

import time
import random
import requests
from typing import List, Dict, Optional
from dataclasses import dataclass
from urllib.parse import quote, urljoin
import sqlite3
import json
from bs4 import BeautifulSoup
import re

# Import existing scrapers
from scrapers.google_maps_scraper import GoogleMapsScraper
from scrapers.yellow_pages_scraper import YellowPagesScraper
from scrapers.linkedin_scraper import LinkedInScraper
from scrapers.facebook_scraper import FacebookScraper
from core.rate_limiter import get_scraper
from core.lead_buckets import LeadBucketManager

@dataclass
class ScrapingSession:
    """Tracks a scraping session with anti-blocking metrics"""
    source: str
    start_time: float
    requests_made: int
    success_rate: float
    blocked_domains: List[str]
    current_proxy: Optional[str]
    user_agent_rotation: int

class AntiBlockingSystem:
    """Advanced anti-blocking mechanisms for web scraping"""
    
    def __init__(self):
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:89.0) Gecko/20100101 Firefox/89.0'
        ]
        
        self.proxy_list = self._load_free_proxies()
        self.current_proxy_index = 0
        self.blocked_domains = set()
        self.request_counts = {}
        self.last_request_times = {}
        
        # Rate limiting per domain
        self.domain_limits = {
            'google.com': {'requests_per_minute': 30, 'requests_per_hour': 1000},
            'yellow.co.in': {'requests_per_minute': 10, 'requests_per_hour': 500},
            'linkedin.com': {'requests_per_minute': 20, 'requests_per_hour': 800},
            'facebook.com': {'requests_per_minute': 15, 'requests_per_hour': 600},
            'justdial.com': {'requests_per_minute': 8, 'requests_per_hour': 300},
            'sulekha.com': {'requests_per_minute': 8, 'requests_per_hour': 300}
        }
    
    def _load_free_proxies(self) -> List[str]:
        """Load free proxy list (for demo purposes)"""
        # In production, integrate with ProxyScrape API or similar service
        return [
            'http://proxy1.example.com:8080',
            'http://proxy2.example.com:8080',
            'http://proxy3.example.com:8080'
        ]
    
    def get_rotating_user_agent(self) -> str:
        """Get a rotating user agent"""
        return random.choice(self.user_agents)
    
    def get_rotating_proxy(self) -> Optional[str]:
        """Get a rotating proxy"""
        if not self.proxy_list:
            return None
        
        proxy = self.proxy_list[self.current_proxy_index]
        self.current_proxy_index = (self.current_proxy_index + 1) % len(self.proxy_list)
        return proxy
    
    def check_rate_limit(self, domain: str) -> bool:
        """Check if we're within rate limits for a domain"""
        current_time = time.time()
        
        if domain not in self.request_counts:
            self.request_counts[domain] = {'minute': 0, 'hour': 0}
            self.last_request_times[domain] = {'minute': current_time, 'hour': current_time}
        
        # Reset counters if time has passed
        if current_time - self.last_request_times[domain]['minute'] > 60:
            self.request_counts[domain]['minute'] = 0
            self.last_request_times[domain]['minute'] = current_time
        
        if current_time - self.last_request_times[domain]['hour'] > 3600:
            self.request_counts[domain]['hour'] = 0
            self.last_request_times[domain]['hour'] = current_time
        
        # Check limits
        limits = self.domain_limits.get(domain, {'requests_per_minute': 10, 'requests_per_hour': 500})
        
        return (self.request_counts[domain]['minute'] < limits['requests_per_minute'] and
                self.request_counts[domain]['hour'] < limits['requests_per_hour'])
    
    def record_request(self, domain: str):
        """Record a request to a domain"""
        if domain in self.request_counts:
            self.request_counts[domain]['minute'] += 1
            self.request_counts[domain]['hour'] += 1
    
    def mark_domain_blocked(self, domain: str):
        """Mark a domain as blocked"""
        self.blocked_domains.add(domain)
        print(f"⚠️  Domain {domain} marked as blocked")
    
    def is_domain_blocked(self, domain: str) -> bool:
        """Check if a domain is blocked"""
        return domain in self.blocked_domains
    
    def add_delay(self, domain: str, base_delay: float = 1.0):
        """Add intelligent delay based on domain and recent activity"""
        # Add random jitter
        jitter = random.uniform(0.5, 2.0)
        
        # Extra delay for high-activity domains
        if domain in self.request_counts:
            minute_activity = self.request_counts[domain].get('minute', 0)
            if minute_activity > 5:  # High activity
                jitter += random.uniform(2.0, 5.0)
        
        time.sleep(base_delay + jitter)

class StageAScraper:
    """Stage A: Intelligent Scraper with Anti-Blocking"""
    
    def __init__(self):
        self.bucket_manager = LeadBucketManager()
        self.anti_blocking = AntiBlockingSystem()
        
        # Initialize individual scrapers
        self.google_scraper = GoogleMapsScraper()
        self.yellow_pages_scraper = YellowPagesScraper()
        self.linkedin_scraper = LinkedInScraper()
        self.facebook_scraper = FacebookScraper()
        
        self.sessions = {}
    
    def create_session(self, source: str) -> ScrapingSession:
        """Create a new scraping session"""
        session = ScrapingSession(
            source=source,
            start_time=time.time(),
            requests_made=0,
            success_rate=0.0,
            blocked_domains=[],
            current_proxy=self.anti_blocking.get_rotating_proxy(),
            user_agent_rotation=0
        )
        self.sessions[source] = session
        return session
    
    def scrape_with_anti_blocking(self, source: str, max_queries: int = 50, plan: List[Dict] = None) -> Dict:
        """Main scraping method with anti-blocking"""
        print(f"=== STAGE A: INTELLIGENT SCRAPER - {source.upper()} ===")
        
        session = self.create_session(source)
        results = {
            'source': source,
            'queries_attempted': 0,
            'leads_found': 0,
            'leads_saved': 0,
            'errors': [],
            'blocked_domains': [],
            'session_duration': 0
        }
        
        start_time = time.time()
        
        try:
            if source == 'google_maps':
                leads = self._scrape_google_maps_safe(max_queries, session, plan=plan)
            elif source == 'yellow_pages':
                leads = self._scrape_yellow_pages_safe(max_queries, session, plan=plan)
            elif source == 'linkedin':
                leads = self._scrape_linkedin_safe(max_queries, session)
            elif source == 'facebook':
                leads = self._scrape_facebook_safe(max_queries, session)
            else:
                raise ValueError(f"Unknown source: {source}")
            
            # Save leads to database
            saved_count = self.google_scraper.save_to_database(leads, source=source)
            
            results.update({
                'leads_found': len(leads),
                'leads_saved': saved_count,
                'queries_attempted': session.requests_made,
                'blocked_domains': list(self.anti_blocking.blocked_domains)
            })
            
        except Exception as e:
            error_msg = f"Scraping {source} failed: {str(e)}"
            results['errors'].append(error_msg)
            print(f"✗ {error_msg}")
        
        finally:
            results['session_duration'] = time.time() - start_time
            session.success_rate = results['leads_saved'] / max(results['leads_found'], 1)
            
            # Log session results
            self._log_session_results(session, results)
        
        return results
    
    def _scrape_google_maps_safe(self, max_queries: int, session: ScrapingSession, plan: List[Dict] = None) -> List[Dict]:
        """Safe Google Maps scraping with anti-blocking"""
        leads = []
        queries = plan if plan else self.bucket_manager.get_search_queries()
        queries = queries[:max_queries]
        
        for i, query in enumerate(queries):
            if self.anti_blocking.is_domain_blocked('google.com'):
                print("⚠️  Google Maps blocked, switching to next source")
                break
            
            if not self.anti_blocking.check_rate_limit('google.com'):
                print("⏸️  Rate limit reached for Google Maps, waiting...")
                time.sleep(60)  # Wait 1 minute
                continue
            
            try:
                # Rotate user agent and proxy
                headers = {'User-Agent': self.anti_blocking.get_rotating_user_agent()}
                session.user_agent_rotation += 1
                
                # Scrape with protection
                query_leads = self.google_scraper.scrape_by_buckets(max_queries_per_bucket=1)
                leads.extend(query_leads)
                
                session.requests_made += 1
                self.anti_blocking.record_request('google.com')
                
                # Add intelligent delay
                self.anti_blocking.add_delay('google.com', 2.0)
                
                print(f"✓ Query {i+1}/{len(queries)}: {len(query_leads)} leads")
                
            except Exception as e:
                if "blocked" in str(e).lower() or "captcha" in str(e).lower():
                    self.anti_blocking.mark_domain_blocked('google.com')
                    break
                else:
                    print(f"⚠️  Error in query {i+1}: {e}")
                    continue
        
        return leads
    
    def _scrape_yellow_pages_safe(self, max_queries: int, session: ScrapingSession, plan: List[Dict] = None) -> List[Dict]:
        """Safe Yellow Pages scraping with anti-blocking"""
        leads = []
        queries = plan if plan else self.bucket_manager.get_search_queries()
        queries = queries[:max_queries]
        
        for i, query in enumerate(queries):
            if self.anti_blocking.is_domain_blocked('yellow.co.in'):
                print("⚠️  Yellow Pages blocked, switching to next source")
                break
            
            if not self.anti_blocking.check_rate_limit('yellow.co.in'):
                print("⏸️  Rate limit reached for Yellow Pages, waiting...")
                time.sleep(60)
                continue
            
            try:
                # Rotate user agent
                headers = {'User-Agent': self.anti_blocking.get_rotating_user_agent()}
                session.user_agent_rotation += 1
                
                # Scrape with protection
                query_leads = self.yellow_pages_scraper.scrape_yellow_directory(max_queries=1)
                leads.extend(query_leads)
                
                session.requests_made += 1
                self.anti_blocking.record_request('yellow.co.in')
                
                # Add intelligent delay
                self.anti_blocking.add_delay('yellow.co.in', 3.0)
                
                print(f"✓ Query {i+1}/{len(queries)}: {len(query_leads)} leads")
                
            except Exception as e:
                if "blocked" in str(e).lower() or "access denied" in str(e).lower():
                    self.anti_blocking.mark_domain_blocked('yellow.co.in')
                    break
                else:
                    print(f"⚠️  Error in query {i+1}: {e}")
                    continue
        
        return leads
    
    def _scrape_linkedin_safe(self, max_queries: int, session: ScrapingSession) -> List[Dict]:
        """Safe LinkedIn scraping with anti-blocking"""
        leads = []
        
        if self.anti_blocking.is_domain_blocked('linkedin.com'):
            print("⚠️  LinkedIn blocked, skipping")
            return leads
        
        try:
            # LinkedIn requires more careful handling
            if not self.anti_blocking.check_rate_limit('linkedin.com'):
                print("⏸️  Rate limit reached for LinkedIn, waiting...")
                time.sleep(60)
            
            leads = self.linkedin_scraper.scrape_linkedin_companies(max_searches=max_queries)
            session.requests_made += 1
            self.anti_blocking.record_request('linkedin.com')
            
            # Longer delay for LinkedIn
            self.anti_blocking.add_delay('linkedin.com', 5.0)
            
        except Exception as e:
            if "blocked" in str(e).lower() or "restricted" in str(e).lower():
                self.anti_blocking.mark_domain_blocked('linkedin.com')
            else:
                print(f"⚠️  LinkedIn scraping error: {e}")
        
        return leads
    
    def _scrape_facebook_safe(self, max_queries: int, session: ScrapingSession) -> List[Dict]:
        """Safe Facebook scraping with anti-blocking"""
        leads = []
        
        if self.anti_blocking.is_domain_blocked('facebook.com'):
            print("⚠️  Facebook blocked, skipping")
            return leads
        
        try:
            if not self.anti_blocking.check_rate_limit('facebook.com'):
                print("⏸️  Rate limit reached for Facebook, waiting...")
                time.sleep(60)
            
            leads = self.facebook_scraper.scrape_by_buckets(max_queries=max_queries)
            session.requests_made += 1
            self.anti_blocking.record_request('facebook.com')
            
            # Longer delay for Facebook
            self.anti_blocking.add_delay('facebook.com', 4.0)
            
        except Exception as e:
            if "blocked" in str(e).lower() or "access denied" in str(e).lower():
                self.anti_blocking.mark_domain_blocked('facebook.com')
            else:
                print(f"⚠️  Facebook scraping error: {e}")
        
        return leads
    
    def _log_session_results(self, session: ScrapingSession, results: Dict):
        """Log session results for analytics"""
        from core.db import log_scraping_session
        
        log_scraping_session(
            source=results['source'],
            query=f"Stage A intelligent scraping - {results['source']}",
            leads_found=results['leads_found'],
            leads_saved=results['leads_saved'],
            error_message=', '.join(results['errors']) if results['errors'] else None
        )
        
        print(f"\n--- {results['source'].upper()} SESSION SUMMARY ---")
        print(f"Duration: {results['session_duration']:.1f}s")
        print(f"Queries Attempted: {results['queries_attempted']}")
        print(f"Leads Found: {results['leads_found']}")
        print(f"Leads Saved: {results['leads_saved']}")
        print(f"Success Rate: {results['leads_saved']/max(results['leads_found'], 1):.1%}")
        if results['blocked_domains']:
            print(f"Blocked Domains: {', '.join(results['blocked_domains'])}")
    
    def run_all_sources(self, max_queries_per_source: int = 50, plan: List[Dict] = None) -> Dict:
        """Run all scraping sources with anti-blocking using an optional plan"""
        print("=== STAGE A: EXECUTION - SCRAPING DISCOVERIES ===")
        
        sources = ['google_maps', 'yellow_pages', 'linkedin', 'facebook']
        # Filter sources based on plan if provided
        if plan:
            print(f"Executing plan with {len(plan)} targeted queries")
        
        all_results = {
            'total_leads_found': 0,
            'total_leads_saved': 0,
            'source_results': {},
            'total_duration': 0,
            'blocked_domains_total': set()
        }
        
        start_time = time.time()
        
        for source in sources:
            print(f"\n{'='*50}")
            # For now, only Google and Yellow Pages use the granular query plan
            plan_for_source = [q for q in plan if q.get('source', 'google_maps') == source] if plan else None
            
            if source == 'google_maps':
                result = self.scrape_with_anti_blocking(source, max_queries_per_source, plan=plan_for_source)
            elif source == 'yellow_pages':
                result = self.scrape_with_anti_blocking(source, max_queries_per_source, plan=plan_for_source)
            else:
                result = self.scrape_with_anti_blocking(source, max_queries_per_source)
                
            all_results['source_results'][source] = result
            all_results['total_leads_found'] += result['leads_found']
            all_results['total_leads_saved'] += result['leads_saved']
            all_results['blocked_domains_total'].update(result['blocked_domains'])
            
            if source != sources[-1]:
                time.sleep(10) # reduced delay
        
        all_results['total_duration'] = time.time() - start_time
        all_results['blocked_domains_total'] = list(all_results['blocked_domains_total'])
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
        print(f"Overall Success Rate: {results['total_leads_saved']/max(results['total_leads_found'], 1):.1%}")
        
        if results['blocked_domains_total']:
            print(f"\n⚠️  Blocked Domains: {', '.join(results['blocked_domains_total'])}")
        
        print(f"\n--- Results by Source ---")
        for source, result in results['source_results'].items():
            print(f"{source.replace('_', ' ').title()}:")
            print(f"  Found: {result['leads_found']}")
            print(f"  Saved: {result['leads_saved']}")
            print(f"  Duration: {result['session_duration']:.1f}s")

if __name__ == '__main__':
    # Demo usage
    scraper = StageAScraper()
    
    print("Stage A: Intelligent Scraper with Anti-Blocking")
    print("Choose an option:")
    print("1. Scrape all sources")
    print("2. Scrape Google Maps only")
    print("3. Scrape Yellow Pages only")
    print("4. Scrape LinkedIn only")
    print("5. Scrape Facebook only")
    
    choice = input("Enter choice (1-5): ").strip()
    
    if choice == '1':
        results = scraper.run_all_sources(max_queries_per_source=20)
    elif choice == '2':
        results = scraper.scrape_with_anti_blocking('google_maps', 50)
    elif choice == '3':
        results = scraper.scrape_with_anti_blocking('yellow_pages', 50)
    elif choice == '4':
        results = scraper.scrape_with_anti_blocking('linkedin', 30)
    elif choice == '5':
        results = scraper.scrape_with_anti_blocking('facebook', 40)
    else:
        print("Invalid choice")
        exit(1)
    
    print(f"\n✅ Stage A completed successfully!")
