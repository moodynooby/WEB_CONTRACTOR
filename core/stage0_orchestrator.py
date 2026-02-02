from datetime import datetime, timedelta
from typing import List, Dict, Optional
import os

from core.lead_buckets import LeadBucketManager
from core.db import log_scraping_session, record_analytic, get_database_stats

class Stage0Orchestrator:
    """Orchestrates Stage 0 lead discovery planning and analytics"""
    
    def __init__(self):
        self.bucket_manager = LeadBucketManager()
        
        # Determine if we need to init DB
        if not os.path.exists('leads.db'):
            from core.db import init_database, populate_buckets
            init_database()
            populate_buckets()

    def get_daily_plan(self, bucket_name: Optional[str] = None, limit: int = 20) -> List[Dict]:
        """Generate a search plan for the day based on targets and current progress"""
        progress = self.get_monthly_progress()
        targets = progress['targets_by_bucket']
        current = progress.get('by_bucket', {})
        
        needed_buckets = []
        if bucket_name:
            needed_buckets = [bucket_name]
        else:
            # Find buckets where we are behind target (simplified)
            for bname, target in targets.items():
                if current.get(bname, 0) < target:
                    needed_buckets.append(bname)
        
        plan = []
        all_queries = self.bucket_manager.get_search_queries()
        
        for bname in needed_buckets:
            bucket_queries = [q for q in all_queries if q['bucket'] == bname]
            # Take a sample for today
            plan.extend(bucket_queries[:limit])
            
        return plan

    def get_discovery_plan(self, daily_mode: bool = True) -> List[Dict]:
        """Generate a lead discovery plan without performing any scraping"""
        print("=== STAGE 0: PLANNING & TARGET GENERATION ===")
        # Double the default limit for daily mode if requested
        limit = 30 if daily_mode else 15
        plan = self.get_daily_plan(limit=limit)
        
        # Record planning analytics
        record_analytic(
            metric_name='daily_plan_queries',
            metric_value=len(plan),
            notes=f"Generated plan with {len(plan)} queries"
        )
        
        return plan
    
    
    def get_monthly_progress(self) -> Dict:
        """Get monthly lead discovery progress"""
        from core.db import LeadRepository
        repo = LeadRepository()
        
        current_month = datetime.now().strftime('%Y-%m')
        stats = repo.get_monthly_stats(current_month)
        
        monthly_total = stats['monthly_total']
        by_source = stats['by_source']
        by_bucket = stats['by_bucket']
        
        targets = self.bucket_manager.get_monthly_targets()
        total_target = sum(targets.values())
        
        return {
            'current_month': current_month,
            'monthly_total': monthly_total,
            'monthly_target': total_target,
            'progress_percentage': monthly_total / max(total_target, 1),
            'by_source': by_source,
            'by_bucket': by_bucket,
            'targets_by_bucket': targets
        }
    
    def run_targeted_plan(self, bucket_name: str, max_queries: int = 50) -> List[Dict]:
        """Generate a targeted discovery plan for a specific bucket"""
        print(f"=== STAGE 0: TARGETED PLANNING - {bucket_name} ===")
        return self.get_daily_plan(bucket_name=bucket_name, limit=max_queries)


