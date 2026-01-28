import time
import json
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import sqlite3
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

    def get_daily_plan(self, bucket_name: Optional[str] = None) -> List[Dict]:
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
            plan.extend(bucket_queries[:10])
            
        return plan

    def get_discovery_plan(self, daily_mode: bool = True) -> List[Dict]:
        """Generate a lead discovery plan without performing any scraping"""
        print("=== STAGE 0: PLANNING & TARGET GENERATION ===")
        plan = self.get_daily_plan()
        
        # Record planning analytics
        record_analytic(
            metric_name='daily_plan_queries',
            metric_value=len(plan),
            notes=f"Generated plan with {len(plan)} queries"
        )
        
        return plan
    
    
    def get_monthly_progress(self) -> Dict:
        """Get monthly lead discovery progress"""
        conn = sqlite3.connect('leads.db')
        cursor = conn.cursor()
        
        current_month = datetime.now().strftime('%Y-%m')
        
        # Monthly total
        cursor.execute("SELECT COUNT(*) FROM leads WHERE created_at LIKE ?", (f"{current_month}%",))
        monthly_total = cursor.fetchone()[0]
        
        # By source
        cursor.execute("SELECT source, COUNT(*) FROM leads WHERE created_at LIKE ? GROUP BY source", (f"{current_month}%",))
        by_source = dict(cursor.fetchall())
        
        # By bucket
        cursor.execute("SELECT bucket, COUNT(*) FROM leads WHERE created_at LIKE ? GROUP BY bucket", (f"{current_month}%",))
        by_bucket = dict(cursor.fetchall())
        
        conn.close()
        
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
    
    def run_targeted_plan(self, bucket_name: str, max_queries: int = 20) -> List[Dict]:
        """Generate a targeted discovery plan for a specific bucket"""
        print(f"=== STAGE 0: TARGETED PLANNING - {bucket_name} ===")
        return self.get_daily_plan(bucket_name=bucket_name)

if __name__ == '__main__':
    orchestrator = Stage0Orchestrator()
    print("Stage 0 Orchestrator - Independent Mode")
    print("Use stage0.py for a better CLI experience.")
    
    progress = orchestrator.get_monthly_progress()
    print(f"\nMonthly Progress: {progress['monthly_total']}/{progress['monthly_target']} ({progress['progress_percentage']:.1%})")
