"""
Main Pipeline Orchestrator
Coordinates all stages and provides unified interface
"""

import time
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import sqlite3

# Import all stages
from core.stage0_orchestrator import Stage0Orchestrator
from scrapers.stage_a_scraper import StageAScraper
from agents.stage_b_auditor import StageBAuditor
from agents.stage_c_messaging import StageCEmailGenerator
from agents.quality_control_agent import QualityControlAgent

# Import utilities
from core.db import get_database_stats, log_scraping_session, record_analytic
from core.lead_buckets import LeadBucketManager

class PipelineOrchestrator:
    """Main pipeline orchestrator that coordinates all stages"""
    
    def __init__(self):
        print("🚀 Initializing Web Contractor Pipeline...")
        
        # Initialize all stages
        self.stage0 = Stage0Orchestrator()
        self.stage_a = StageAScraper()
        self.stage_b = StageBAuditor()
        self.stage_c = StageCEmailGenerator()
        self.quality_control = QualityControlAgent()
        
        # Pipeline state
        self.pipeline_state = {
            'running': False,
            'current_stage': None,
            'last_run': None,
            'total_runs': 0,
            'errors': []
        }
        
        # Stage configurations
        self.stage_configs = {
            'stage0': {
                'enabled': True,
                'schedule': 'daily',  # daily, weekly, manual
                'priority': 1,
                'max_runtime_minutes': 60
            },
            'stage_a': {
                'enabled': True,
                'schedule': 'daily',
                'priority': 2,
                'max_runtime_minutes': 120
            },
            'stage_b': {
                'enabled': True,
                'schedule': 'daily',
                'priority': 3,
                'max_runtime_minutes': 90
            },
            'stage_c': {
                'enabled': True,
                'schedule': 'daily',
                'priority': 4,
                'max_runtime_minutes': 60
            },
            'quality_control': {
                'enabled': True,
                'schedule': 'hourly',
                'priority': 5,
                'max_runtime_minutes': 15
            }
        }
        
        print("✅ Pipeline initialized successfully")
    
    def run_full_pipeline(self, manual_mode: bool = False) -> Dict:
        """Run complete pipeline from Stage 0 to Stage C"""
        print("\n" + "="*80)
        print("🔄 RUNNING FULL PIPELINE")
        print("="*80)
        print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        if self.pipeline_state['running']:
            print("⚠️  Pipeline already running!")
            return {'status': 'already_running', 'results': {}}
        
        self.pipeline_state['running'] = True
        self.pipeline_state['last_run'] = datetime.now()
        
        results = {
            'pipeline_start': datetime.now().isoformat(),
            'stages_completed': [],
            'stages_failed': [],
            'total_leads_generated': 0,
            'total_leads_audited': 0,
            'total_emails_generated': 0,
            'quality_issues': 0,
            'duration': 0,
            'errors': []
        }
        
        try:
            # Stage 0: Planning & Target Generation
            if self.stage_configs['stage0']['enabled']:
                self.pipeline_state['current_stage'] = 'Stage 0'
                print(f"\n📍 STAGE 0: PLANNING & TARGET GENERATION")
                
                try:
                    plan = self.stage0.get_discovery_plan(daily_mode=not manual_mode)
                    results['stages_completed'].append('Stage 0')
                    print(f"✅ Stage 0 completed: Generated plan with {len(plan)} queries")
                    
                    # Stage A: Execution - Intelligent Scraper
                    if self.stage_configs['stage_a']['enabled']:
                        self.pipeline_state['current_stage'] = 'Stage A'
                        print(f"\n🔍 STAGE A: EXECUTION - INTELLIGENT SCRAPER")
                        
                        stage_a_results = self.stage_a.run_all_sources(
                            max_queries_per_source=50 if manual_mode else 100,
                            plan=plan
                        )
                        results['stages_completed'].append('Stage A')
                        results['total_leads_generated'] = stage_a_results.get('total_leads_saved', 0)
                        print(f"✅ Stage A completed: {results['total_leads_generated']} leads saved")
                except Exception as e:
                    error_msg = f"Discovery flow failed: {str(e)}"
                    results['stages_failed'].append('Stage 0/A')
                    results['errors'].append(error_msg)
                    print(f"❌ {error_msg}")
            
            # Stage B: 'Needs Update' Auditor Engine
            if self.stage_configs['stage_b']['enabled']:
                self.pipeline_state['current_stage'] = 'Stage B'
                print(f"\n🔧 STAGE B: 'NEEDS UPDATE' AUDITOR ENGINE")
                
                try:
                    stage_b_results = self.stage_b.audit_pending_leads(batch_size=100 if manual_mode else 200)
                    results['stages_completed'].append('Stage B')
                    results['total_leads_audited'] = stage_b_results.get('audited_count', 0)
                    print(f"✅ Stage B completed: {results['total_leads_audited']} leads audited")
                    print(f"📊 Qualified leads: {stage_b_results.get('qualified_count', 0)}")
                except Exception as e:
                    error_msg = f"Stage B failed: {str(e)}"
                    results['stages_failed'].append('Stage B')
                    results['errors'].append(error_msg)
                    print(f"❌ {error_msg}")
            
            # Stage C: AI-Powered Messaging
            if self.stage_configs['stage_c']['enabled']:
                self.pipeline_state['current_stage'] = 'Stage C'
                print(f"\n📧 STAGE C: AI-POWERED MESSAGING")
                
                try:
                    stage_c_results = self.stage_c.generate_emails_for_qualified_leads(batch_size=50 if manual_mode else 100)
                    results['stages_completed'].append('Stage C')
                    results['total_emails_generated'] = stage_c_results.get('generated_count', 0)
                    print(f"✅ Stage C completed: {results['total_emails_generated']} emails generated")
                except Exception as e:
                    error_msg = f"Stage C failed: {str(e)}"
                    results['stages_failed'].append('Stage C')
                    results['errors'].append(error_msg)
                    print(f"❌ {error_msg}")
            
            # Quality Control
            if self.stage_configs['quality_control']['enabled']:
                self.pipeline_state['current_stage'] = 'Quality Control'
                print(f"\n🛡️  QUALITY CONTROL")
                
                try:
                    qc_results = self.quality_control.run_quality_check(comprehensive=True)
                    results['stages_completed'].append('Quality Control')
                    results['quality_issues'] = qc_results.get('total_alerts', 0)
                    print(f"✅ Quality Control completed: {results['quality_issues']} issues found")
                except Exception as e:
                    error_msg = f"Quality Control failed: {str(e)}"
                    results['stages_failed'].append('Quality Control')
                    results['errors'].append(error_msg)
                    print(f"❌ {error_msg}")
            
            # Calculate total duration
            results['duration'] = (datetime.now() - datetime.fromisoformat(results['pipeline_start'])).total_seconds()
            
            # Print final summary
            self._print_pipeline_summary(results)
            
            # Update pipeline state
            self.pipeline_state['total_runs'] += 1
            self.pipeline_state['errors'] = results['errors']
            
            # Record pipeline analytics
            self._record_pipeline_analytics(results)
            
        except Exception as e:
            error_msg = f"Pipeline failed: {str(e)}"
            results['errors'].append(error_msg)
            print(f"💥 CRITICAL ERROR: {error_msg}")
        
        finally:
            self.pipeline_state['running'] = False
            self.pipeline_state['current_stage'] = None
        
        return results
    
    def run_individual_stage(self, stage_name: str, **kwargs) -> Dict:
        """Run individual stage"""
        stage_map = {
            'stage0': self.stage0,
            'stage_a': self.stage_a,
            'stage_b': self.stage_b,
            'stage_c': self.stage_c,
            'quality_control': self.quality_control
        }
        
        if stage_name not in stage_map:
            return {'error': f'Unknown stage: {stage_name}'}
        
        if not self.stage_configs[stage_name]['enabled']:
            return {'error': f'Stage {stage_name} is disabled'}
        
        print(f"\n🔄 Running {stage_name.upper()}...")
        
        try:
            if stage_name == 'stage0':
                results = self.stage0.get_discovery_plan(**kwargs)
            elif stage_name == 'stage_a':
                # If stage_a is run individually, it can get its own plan if none provided
                results = self.stage_a.run_all_sources(**kwargs)
            elif stage_name == 'stage_b':
                results = self.stage_b.audit_pending_leads(**kwargs)
            elif stage_name == 'stage_c':
                results = self.stage_c.generate_emails_for_qualified_leads(**kwargs)
            elif stage_name == 'quality_control':
                results = self.quality_control.run_quality_check(**kwargs)
            
            print(f"✅ {stage_name.upper()} completed successfully")
            return {'status': 'success', 'results': results}
            
        except Exception as e:
            error_msg = f"{stage_name.upper()} failed: {str(e)}"
            print(f"❌ {error_msg}")
            return {'status': 'error', 'error': error_msg}
    
    def get_pipeline_status(self) -> Dict:
        """Get current pipeline status"""
        # Get database stats
        db_stats = get_database_stats()
        
        # Get quality dashboard
        quality_dashboard = self.quality_control.get_quality_dashboard()
        
        # Get stage-specific stats
        stage_stats = {}
        
        # Stage 0 stats
        stage_stats['stage0'] = self.stage0.get_monthly_progress()
        
        # Stage B stats
        stage_stats['stage_b'] = self.stage_b.get_audit_statistics()
        
        # Stage C stats
        stage_stats['stage_c'] = self.stage_c.get_email_statistics()
        
        return {
            'pipeline_state': self.pipeline_state,
            'database_stats': db_stats,
            'quality_dashboard': quality_dashboard,
            'stage_stats': stage_stats,
            'stage_configs': self.stage_configs,
            'last_quality_check': datetime.now().isoformat()
        }
    
    def _print_pipeline_summary(self, results: Dict):
        """Print pipeline execution summary"""
        print(f"\n{'='*80}")
        print("📊 PIPELINE EXECUTION SUMMARY")
        print(f"{'='*80}")
        print(f"Duration: {results['duration']:.1f} seconds")
        print(f"Stages Completed: {len(results['stages_completed'])}")
        print(f"Stages Failed: {len(results['stages_failed'])}")
        
        if results['stages_completed']:
            print(f"\n✅ COMPLETED STAGES:")
            for stage in results['stages_completed']:
                print(f"  • {stage}")
        
        if results['stages_failed']:
            print(f"\n❌ FAILED STAGES:")
            for stage in results['stages_failed']:
                print(f"  • {stage}")
        
        print(f"\n📈 RESULTS:")
        print(f"  Total Leads Generated: {results['total_leads_generated']}")
        print(f"  Total Leads Audited: {results['total_leads_audited']}")
        print(f"  Total Emails Generated: {results['total_emails_generated']}")
        print(f"  Quality Issues Found: {results['quality_issues']}")
        
        if results['errors']:
            print(f"\n⚠️  ERRORS:")
            for error in results['errors'][:5]:  # Show first 5 errors
                print(f"  • {error}")
        
        # Success metrics
        if results['total_leads_generated'] > 0:
            audit_rate = results['total_leads_audited'] / results['total_leads_generated']
            email_rate = results['total_emails_generated'] / max(results['total_leads_audited'], 1)
            
            print(f"\n📊 SUCCESS METRICS:")
            print(f"  Audit Coverage: {audit_rate:.1%}")
            print(f"  Email Coverage: {email_rate:.1%}")
    
    def _record_pipeline_analytics(self, results: Dict):
        """Record pipeline execution analytics"""
        # Overall pipeline metrics
        record_analytic(
            metric_name='pipeline_duration',
            metric_value=results['duration'],
            notes=f"Pipeline completed in {results['duration']:.1f}s"
        )
        
        record_analytic(
            metric_name='pipeline_stages_completed',
            metric_value=len(results['stages_completed']),
            notes=f"Stages: {', '.join(results['stages_completed'])}"
        )
        
        record_analytic(
            metric_name='pipeline_stages_failed',
            metric_value=len(results['stages_failed']),
            notes=f"Failed: {', '.join(results['stages_failed'])}" if results['stages_failed'] else "None"
        )
        
        # Stage-specific metrics
        if results['total_leads_generated'] > 0:
            record_analytic(
                metric_name='leads_generated_per_run',
                metric_value=results['total_leads_generated'],
                notes="Total leads from Stage 0 + Stage A"
            )
        
        if results['total_leads_audited'] > 0:
            record_analytic(
                metric_name='leads_audited_per_run',
                metric_value=results['total_leads_audited'],
                notes="Total leads audited in Stage B"
            )
        
        if results['total_emails_generated'] > 0:
            record_analytic(
                metric_name='emails_generated_per_run',
                metric_value=results['total_emails_generated'],
                notes="Total emails generated in Stage C"
            )
        
        if results['quality_issues'] > 0:
            record_analytic(
                metric_name='quality_issues_per_run',
                metric_value=results['quality_issues'],
                notes="Issues found by Quality Control"
            )
    
    def schedule_pipeline_run(self, schedule_type: str = 'daily') -> Dict:
        """Schedule pipeline runs (placeholder for future implementation)"""
        print(f"📅 Pipeline scheduling ({schedule_type}) - Feature coming soon!")
        return {
            'status': 'scheduled',
            'schedule_type': schedule_type,
            'next_run': 'TBD'
        }
    
    def get_pipeline_recommendations(self) -> List[str]:
        """Get pipeline optimization recommendations"""
        recommendations = []
        status = self.get_pipeline_status()
        
        # Check for bottlenecks
        db_stats = status['database_stats']
        
        if db_stats.get('leads_by_status', {}).get('pending_audit', 0) > 100:
            recommendations.append("🔧 Run Stage B auditor - large backlog of pending audits")
        
        qualified_leads = db_stats.get('leads_by_status', {}).get('qualified', 0)
        total_emails = db_stats.get('emails_by_status', {}).get('total', 0)
        
        if qualified_leads > total_emails + 20:
            recommendations.append("📧 Run Stage C email generator - qualified leads waiting for emails")
        
        # Check quality issues
        quality_issues = status['quality_dashboard']['recent_alerts']
        if quality_issues > 5:
            recommendations.append("🛡️  Run Quality Control - multiple recent issues detected")
        
        # Check pipeline health
        if status['pipeline_state']['errors']:
            recommendations.append("🔍 Review pipeline errors - some stages are failing")
        
        # Performance recommendations
        stage_stats = status.get('stage_stats', {})
        if stage_stats.get('stage_b', {}).get('qualification_rate', 0) < 0.3:
            recommendations.append("🎯 Review lead quality - low qualification rate")
        
        if stage_stats.get('stage_c', {}).get('personalization_avg', 0) < 0.6:
            recommendations.append("✍️  Improve email personalization - low personalization scores")
        
        if not recommendations:
            recommendations.append("✅ Pipeline running smoothly - no immediate actions needed")
        
        return recommendations

if __name__ == '__main__':
    # Demo usage
    orchestrator = PipelineOrchestrator()
    
    print("🚀 Web Contractor Pipeline Orchestrator")
    print("Choose an option:")
    print("1. Run full pipeline")
    print("2. Run individual stage")
    print("3. Get pipeline status")
    print("4. Get recommendations")
    print("5. Run quality check only")
    
    choice = input("Enter choice (1-5): ").strip()
    
    if choice == '1':
        print("Running full pipeline...")
        results = orchestrator.run_full_pipeline(manual_mode=True)
        print(f"\n🎉 Pipeline completed!")
    elif choice == '2':
        print("Available stages: stage0, stage_a, stage_b, stage_c, quality_control")
        stage = input("Enter stage name: ").strip()
        results = orchestrator.run_individual_stage(stage)
        if results['status'] == 'success':
            print(f"✅ {stage} completed successfully")
        else:
            print(f"❌ {stage} failed: {results.get('error', 'Unknown error')}")
    elif choice == '3':
        status = orchestrator.get_pipeline_status()
        print(f"\n=== PIPELINE STATUS ===")
        print(f"Running: {status['pipeline_state']['running']}")
        print(f"Total Runs: {status['pipeline_state']['total_runs']}")
        print(f"Last Run: {status['pipeline_state']['last_run']}")
        
        print(f"\n--- Database Stats ---")
        db_stats = status['database_stats']
        if 'leads_by_status' in db_stats:
            print(f"Leads by Status: {db_stats['leads_by_status']}")
        if 'leads_by_source' in db_stats:
            print(f"Leads by Source: {db_stats['leads_by_source']}")
        
        print(f"\n--- Quality Dashboard ---")
        quality = status['quality_dashboard']
        print(f"Total Leads: {quality['total_leads']}")
        print(f"Qualified: {quality['qualified_leads']}")
        print(f"Emails: {quality['total_emails']}")
        print(f"Qualification Rate: {quality['qualification_rate']:.1%}")
    elif choice == '4':
        recommendations = orchestrator.get_pipeline_recommendations()
        print(f"\n=== RECOMMENDATIONS ===")
        for rec in recommendations:
            print(rec)
    elif choice == '5':
        results = orchestrator.quality_control.run_quality_check(comprehensive=True)
        print(f"\n🛡️  Quality check completed: {results['total_alerts']} issues found")
    else:
        print("Invalid choice")
