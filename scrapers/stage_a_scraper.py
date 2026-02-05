"""
Stage A: Intelligent Scraper Execution
Executes the discovery plan across multiple high-quality sources with rate limiting
"""

import time
from typing import List, Dict
from dataclasses import dataclass
from scrapers.google_maps_scraper import GoogleMapsScraper
from scrapers.yellow_pages_scraper import YellowPagesScraper
from scrapers.bbb_scraper import BBBScraper
from scrapers.yelp_scraper import YelpScraper
from scrapers.facebook_business_scraper import FacebookBusinessScraper
from scrapers.linkedin_company_scraper import LinkedInCompanyScraper
from scrapers.industry_directory_scraper import IndustryDirectoryScraper
from core.lead_buckets import LeadBucketManager
from core.db import LeadRepository


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
    """Stage A: Intelligent Scraper Orchestrator with Enhanced Sources"""

    def __init__(self):
        self.bucket_manager = LeadBucketManager()
        self.repo = LeadRepository()

        # Initialize all scrapers (sorted by quality/reliability)
        self.google_scraper = GoogleMapsScraper()
        self.yellow_pages_scraper = YellowPagesScraper()
        self.bbb_scraper = BBBScraper()
        self.yelp_scraper = YelpScraper()
        self.facebook_scraper = FacebookBusinessScraper()
        self.linkedin_scraper = LinkedInCompanyScraper()
        self.industry_directory_scraper = IndustryDirectoryScraper()

    def scrape_source(
        self, source: str, max_queries: int = 50, plan: List[Dict] = None
    ) -> Dict:
        """Execute scraping for a specific source"""
        print(f"\n=== STAGE A: EXECUTING {source.upper()} ===")

        session = ScrapingSession(source=source, start_time=time.time())
        leads = []

        try:
            if source == "google_maps":
                leads = self.google_scraper.scrape_by_buckets(
                    max_queries_per_bucket=5, plan=plan
                )
            elif source == "yellow_pages":
                leads = self.yellow_pages_scraper.scrape_by_buckets(
                    max_queries_per_bucket=5
                )
            elif source == "bbb":
                leads = self.bbb_scraper.scrape_by_buckets(
                    max_queries_per_bucket=4
                )
            elif source == "yelp":
                leads = self.yelp_scraper.scrape_by_buckets(
                    max_queries_per_bucket=4
                )
            elif source == "facebook_business":
                leads = self.facebook_scraper.scrape_by_buckets(
                    max_queries_per_bucket=3
                )
            elif source == "linkedin_company":
                leads = self.linkedin_scraper.scrape_by_buckets(
                    max_queries_per_bucket=3
                )
            elif source == "industry_directory":
                leads = self.industry_directory_scraper.scrape_by_buckets(
                    max_queries_per_bucket=4
                )
            else:
                raise ValueError(f"Unknown source: {source}")

            # Save leads (individual scrapers handle their own saving, but we can aggregate)
            session.leads_found = len(leads)
            # Individual scrapers already saved to DB in their main methods,
            # but we can call save_to_database again if we want to be sure or log it.
            # For now, we rely on the scraper's internal saving.
            session.leads_saved = len(leads)  # Simplified

        except Exception as e:
            error_msg = f"Scraping {source} failed: {str(e)}"
            session.errors.append(error_msg)
            print(f"✗ {error_msg}")

        results = {
            "source": source,
            "leads_found": session.leads_found,
            "leads_saved": session.leads_saved,
            "duration": time.time() - session.start_time,
            "errors": session.errors,
        }

        # Log session results
        self.repo.log_scraping_session(
            source=source,
            query="Stage A scraping session",
            leads_found=session.leads_found,
            leads_saved=session.leads_saved,
            error_message=", ".join(session.errors) if session.errors else None,
        )

        return results

    def run_all_sources(
        self, max_queries_per_source: int = 20, plan: List[Dict] = None
    ) -> Dict:
        """Run all active scraping sources in priority order"""
        print("=== STAGE A: ENHANCED SCRAPING - MULTI-SOURCE EXECUTION ===")

        # Enhanced sources in quality order (high to lower)
        sources = [
            "bbb",           # Highest quality - verified businesses
            "yelp",          # High quality - review data & social proof
            "google_maps",   # Good quality - comprehensive local data
            "linkedin_company", # B2B focused - company data
            "facebook_business", # Social proof - engagement data
            "yellow_pages",  # Standard quality - directory listings
            "industry_directory", # Specialized - industry specific
        ]
        
        all_results = {
            "total_leads_found": 0,
            "total_leads_saved": 0,
            "source_results": {},
            "total_duration": 0,
            "enhanced_features": [
                "BBB verified businesses with accreditation",
                "Yelp review data and social proof",
                "LinkedIn company size and industry data",
                "Facebook social engagement metrics",
                "Industry-specific professional directories",
                "Enhanced quality scoring algorithms",
                "Improved deduplication and validation"
            ]
        }

        start_time = time.time()

        for source in sources:
            result = self.scrape_source(source, max_queries_per_source, plan=plan)
            all_results["source_results"][source] = result
            all_results["total_leads_found"] += result["leads_found"]
            all_results["total_leads_saved"] += result["leads_saved"]

            # Extended delay between sources for better rate limiting
            if source != sources[-1]:
                time.sleep(8)

        all_results["total_duration"] = time.time() - start_time
        self._print_final_summary(all_results)
        return all_results

    def _print_final_summary(self, results: Dict):
        """Print comprehensive final summary for all enhanced sources"""
        print(f"\n{'=' * 70}")
        print("STAGE A: ENHANCED INTELLIGENT SCRAPER - FINAL SUMMARY")
        print(f"{'=' * 70}")
        print(f"Total Duration: {results['total_duration']:.1f}s")
        print(f"Total Leads Found: {results['total_leads_found']}")
        print(f"Total Leads Saved: {results['total_leads_saved']}")

        print(f"\n🎯 ENHANCED FEATURES:")
        for feature in results.get("enhanced_features", []):
            print(f"  ✓ {feature}")

        print(f"\n--- Results by Source (Quality Order) ---")
        source_quality_order = [
            ("bbb", "🏆 BBB - Verified Businesses (Highest Quality)"),
            ("yelp", "⭐ Yelp - Review Data & Social Proof"),
            ("google_maps", "🗺️ Google Maps - Comprehensive Local Data"),
            ("linkedin_company", "💼 LinkedIn - B2B Company Intelligence"),
            ("facebook_business", "📘 Facebook - Social Engagement Metrics"),
            ("yellow_pages", "📋 Yellow Pages - Directory Listings"),
            ("industry_directory", "🎯 Industry Directories - Specialized Sources"),
        ]
        
        for source_key, source_title in source_quality_order:
            if source_key in results["source_results"]:
                result = results["source_results"][source_key]
                errors_info = f" (⚠️ {len(result['errors'])} errors)" if result["errors"] else ""
                print(f"{source_title}")
                print(f"    Found: {result['leads_found']} | Saved: {result['leads_saved']} | Duration: {result['duration']:.1f}s{errors_info}")
                if result["errors"]:
                    for error in result["errors"][:2]:  # Show first 2 errors
                        print(f"    Error: {error}")
                    if len(result["errors"]) > 2:
                        print(f"    ... and {len(result['errors']) - 2} more errors")

        print(f"\n{'=' * 70}")
        print("🚀 ENHANCED SCRAPING COMPLETE - Higher Quality Lead Generation!")
        print(f"{'=' * 70}")
