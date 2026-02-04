"""
Main Pipeline Orchestrator
Coordinates all stages and provides unified interface
"""

from datetime import datetime
from typing import Dict, List

# Import all stages
from core.stage0_orchestrator import Stage0Orchestrator
from scrapers.stage_a_scraper import StageAScraper
from agents.stage_b_auditor import StageBAuditor
from agents.stage_c_messaging import StageCEmailGenerator

# Import utilities
from core.db import LeadRepository
import threading


class PipelineOrchestrator:
    """Main pipeline orchestrator that coordinates all stages"""

    def __init__(self):
        print("🚀 Initializing Web Contractor Pipeline...")
        self.repo = LeadRepository()

        # Initialize all stages
        self.stage0 = Stage0Orchestrator()
        self.stage_a = StageAScraper()
        self.stage_b = StageBAuditor()
        self.stage_c = StageCEmailGenerator()
        self.processes = {
            "full_pipeline": {
                "running": False,
                "thread": None,
                "start_time": None,
                "progress": 0,
            },
            "stage0": {
                "running": False,
                "thread": None,
                "start_time": None,
                "progress": 0,
            },
            "stage_a": {
                "running": False,
                "thread": None,
                "start_time": None,
                "progress": 0,
            },
            "stage_b": {
                "running": False,
                "thread": None,
                "start_time": None,
                "progress": 0,
            },
            "stage_c": {
                "running": False,
                "thread": None,
                "start_time": None,
                "progress": 0,
            },
            "email_sender": {
                "running": False,
                "thread": None,
                "start_time": None,
                "progress": 0,
            },
        }

        # Pipeline state
        self.pipeline_state = {
            "running": False,
            "current_stage": None,
            "last_run": None,
            "total_runs": 0,
            "errors": [],
        }

        # Stage configurations
        self.stage_configs = {
            "stage0": {
                "enabled": True,
                "schedule": "daily",  # daily, weekly, manual
                "priority": 1,
                "max_runtime_minutes": 60,
            },
            "stage_a": {
                "enabled": True,
                "schedule": "daily",
                "priority": 2,
                "max_runtime_minutes": 120,
            },
            "stage_b": {
                "enabled": True,
                "schedule": "daily",
                "priority": 3,
                "max_runtime_minutes": 90,
            },
            "stage_c": {
                "enabled": True,
                "schedule": "daily",
                "priority": 4,
                "max_runtime_minutes": 60,
            },
        }

        print("✅ Pipeline initialized successfully")

    def run_full_pipeline(self, manual_mode: bool = False) -> Dict:
        """Run complete pipeline from Stage 0 to Stage C"""
        print("\n" + "=" * 80)
        print("🔄 RUNNING FULL PIPELINE")
        print("=" * 80)
        print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        if self.pipeline_state["running"]:
            print("⚠️  Pipeline already running!")
            return {"status": "already_running", "results": {}}

        self.pipeline_state["running"] = True
        self.pipeline_state["last_run"] = datetime.now()

        results = {
            "pipeline_start": datetime.now().isoformat(),
            "stages_completed": [],
            "stages_failed": [],
            "total_leads_generated": 0,
            "total_leads_audited": 0,
            "total_emails_generated": 0,
            "quality_issues": 0,
            "duration": 0,
            "errors": [],
        }

        try:
            # Stage 0: Planning & Target Generation
            if self.stage_configs["stage0"]["enabled"]:
                self.pipeline_state["current_stage"] = "Stage 0"
                print("\n📍 STAGE 0: PLANNING & TARGET GENERATION")

                try:
                    plan = self.stage0.get_discovery_plan(daily_mode=not manual_mode)
                    results["stages_completed"].append("Stage 0")
                    print(
                        f"✅ Stage 0 completed: Generated plan with {len(plan)} queries"
                    )

                    # Stage A: Execution - Intelligent Scraper
                    if self.stage_configs["stage_a"]["enabled"]:
                        self.pipeline_state["current_stage"] = "Stage A"
                        print("\n🔍 STAGE A: EXECUTION - INTELLIGENT SCRAPER")

                        stage_a_results = self.stage_a.run_all_sources(
                            max_queries_per_source=50 if manual_mode else 100, plan=plan
                        )
                        results["stages_completed"].append("Stage A")
                        results["total_leads_generated"] = stage_a_results.get(
                            "total_leads_saved", 0
                        )
                        print(
                            f"✅ Stage A completed: {results['total_leads_generated']} leads saved"
                        )
                except Exception as e:
                    error_msg = f"Discovery flow failed: {str(e)}"
                    results["stages_failed"].append("Stage 0/A")
                    results["errors"].append(error_msg)
                    print(f"❌ {error_msg}")

            # Stage B: 'Needs Update' Auditor Engine
            if self.stage_configs["stage_b"]["enabled"]:
                self.pipeline_state["current_stage"] = "Stage B"
                print("\n🔧 STAGE B: 'NEEDS UPDATE' AUDITOR ENGINE")

                try:
                    stage_b_results = self.stage_b.audit_pending_leads(
                        batch_size=100 if manual_mode else 200
                    )
                    results["stages_completed"].append("Stage B")
                    results["total_leads_audited"] = stage_b_results.get(
                        "audited_count", 0
                    )
                    print(
                        f"✅ Stage B completed: {results['total_leads_audited']} leads audited"
                    )
                    print(
                        f"📊 Qualified leads: {stage_b_results.get('qualified_count', 0)}"
                    )
                except Exception as e:
                    error_msg = f"Stage B failed: {str(e)}"
                    results["stages_failed"].append("Stage B")
                    results["errors"].append(error_msg)
                    print(f"❌ {error_msg}")

            # Stage C: AI-Powered Messaging
            if self.stage_configs["stage_c"]["enabled"]:
                self.pipeline_state["current_stage"] = "Stage C"
                print("\n📧 STAGE C: AI-POWERED MESSAGING")

                try:
                    stage_c_results = self.stage_c.generate_emails_for_qualified_leads(
                        batch_size=50 if manual_mode else 100
                    )
                    results["stages_completed"].append("Stage C")
                    results["total_emails_generated"] = stage_c_results.get(
                        "generated_count", 0
                    )
                    print(
                        f"✅ Stage C completed: {results['total_emails_generated']} emails generated"
                    )
                except Exception as e:
                    error_msg = f"Stage C failed: {str(e)}"
                    results["stages_failed"].append("Stage C")
                    results["errors"].append(error_msg)
                    print(f"❌ {error_msg}")

            # Calculate total duration
            results["duration"] = (
                datetime.now() - datetime.fromisoformat(results["pipeline_start"])
            ).total_seconds()

            # Print final summary
            self._print_pipeline_summary(results)

            # Update pipeline state
            self.pipeline_state["total_runs"] += 1
            self.pipeline_state["errors"] = results["errors"]

            # Record pipeline analytics
            self._record_pipeline_analytics(results)

        except Exception as e:
            error_msg = f"Pipeline failed: {str(e)}"
            results["errors"].append(error_msg)
            print(f"💥 CRITICAL ERROR: {error_msg}")

        finally:
            self.pipeline_state["running"] = False
            self.pipeline_state["current_stage"] = None

        return results

    def run_individual_stage(self, stage_name: str, **kwargs) -> Dict:
        """Run individual stage with global concurrency check"""
        stage_map = {
            "stage0": self.stage0,
            "stage_a": self.stage_a,
            "stage_b": self.stage_b,
            "stage_c": self.stage_c,
        }

        if stage_name not in stage_map:
            return {"error": f"Unknown stage: {stage_name}"}

        if not self.stage_configs[stage_name]["enabled"]:
            return {"error": f"Stage {stage_name} is disabled"}

        # Global Concurrency Lock Check
        if self.pipeline_state["running"]:
            error_msg = f"Cannot start {stage_name}: Pipeline is already running (Current stage: {self.pipeline_state['current_stage']})"
            print(f"⚠️  {error_msg}")
            # Throwing an exception is cleaner for the API to catch,
            # but maintaining dict return signature for compatibility with existing calls if any.
            # Ideally, we should unify this. For now, let's return error dict.
            # Raising generic exception to be caught by main.py wrapper to ensure it's treated as 400
            raise Exception("Pipeline already running")

        print(f"\n🔄 Running {stage_name.upper()}...")

        # Set Lock
        self.pipeline_state["running"] = True
        self.pipeline_state["current_stage"] = stage_name
        self.pipeline_state["last_run"] = datetime.now()

        try:
            if stage_name == "stage0":
                results = self.stage0.get_discovery_plan(**kwargs)
            elif stage_name == "stage_a":
                # If stage_a is run individually, it can get its own plan if none provided
                results = self.stage_a.run_all_sources(**kwargs)
            elif stage_name == "stage_b":
                results = self.stage_b.audit_pending_leads(**kwargs)
            elif stage_name == "stage_c":
                results = self.stage_c.generate_emails_for_qualified_leads(**kwargs)

            print(f"✅ {stage_name.upper()} completed successfully")
            return {"status": "success", "results": results}

        except Exception as e:
            error_msg = f"{stage_name.upper()} failed: {str(e)}"
            print(f"❌ {error_msg}")
            return {"status": "error", "error": error_msg}
        finally:
            # Release Lock
            self.pipeline_state["running"] = False
            self.pipeline_state["current_stage"] = None

    def start_process(self, process_key: str, **kwargs) -> bool:
        """Start a pipeline process in a background thread"""
        if process_key not in self.processes:
            return False

        if self.processes[process_key]["running"] or (
            self.pipeline_state["running"] and process_key != "email_sender"
        ):
            return False

        def run_wrapper():
            try:
                self.processes[process_key]["running"] = True
                self.processes[process_key]["start_time"] = datetime.now()
                self.processes[process_key]["progress"] = 0

                if process_key == "full_pipeline":
                    self.run_full_pipeline(manual_mode=True)
                elif process_key == "email_sender":
                    # Special case for email sender which needs mail instance injected
                    # This should be handled by the caller or specialized method
                    pass
                else:
                    self.run_individual_stage(process_key, **kwargs)

                self.processes[process_key]["progress"] = 100
            except Exception as e:
                print(f"Process {process_key} failed: {e}")
            finally:
                self.processes[process_key]["running"] = False
                self.processes[process_key]["thread"] = None
                if process_key != "email_sender":
                    self.pipeline_state["running"] = False

        thread = threading.Thread(target=run_wrapper)
        thread.daemon = True
        thread.start()

        self.processes[process_key]["thread"] = thread
        if process_key != "email_sender":
            self.pipeline_state["running"] = True
            self.pipeline_state["current_stage"] = process_key

        return True

    def stop_process(self, process_key: str) -> bool:
        """Stop a running process"""
        if (
            process_key not in self.processes
            or not self.processes[process_key]["running"]
        ):
            return False

        # Simplistic stop (doesn't kill the thread, just marks it as stopped for UI)
        self.processes[process_key]["running"] = False
        self.processes[process_key]["progress"] = 0
        if process_key != "email_sender":
            self.pipeline_state["running"] = False
            self.pipeline_state["current_stage"] = None
        return True

    def get_process_status(self) -> Dict:
        """Get status of all processes"""
        status = {}
        for key, process in self.processes.items():
            status[key] = {
                "running": process["running"],
                "progress": process["progress"],
                "start_time": process["start_time"].isoformat()
                if process["start_time"]
                else None,
            }
        return status

    def get_pipeline_status(self) -> Dict:
        """Get current pipeline status"""
        # Get database stats
        db_stats = get_database_stats()

        # Get stage-specific stats
        stage_stats = {}

        # Stage 0 stats
        stage_stats["stage0"] = self.stage0.get_monthly_progress()

        # Stage B stats
        stage_stats["stage_b"] = self.stage_b.get_audit_statistics()

        # Stage C stats
        stage_stats["stage_c"] = self.stage_c.get_email_statistics()

        return {
            "pipeline_state": self.pipeline_state,
            "database_stats": db_stats,
            "stage_stats": stage_stats,
            "stage_configs": self.stage_configs,
            "last_run_check": datetime.now().isoformat(),
        }

    def _print_pipeline_summary(self, results: Dict):
        """Print pipeline execution summary"""
        print(f"\n{'=' * 80}")
        print("📊 PIPELINE EXECUTION SUMMARY")
        print(f"{'=' * 80}")
        print(f"Duration: {results['duration']:.1f} seconds")
        print(f"Stages Completed: {len(results['stages_completed'])}")
        print(f"Stages Failed: {len(results['stages_failed'])}")

        if results["stages_completed"]:
            print("\n✅ COMPLETED STAGES:")
            for stage in results["stages_completed"]:
                print(f"  • {stage}")

        if results["stages_failed"]:
            print("\n❌ FAILED STAGES:")
            for stage in results["stages_failed"]:
                print(f"  • {stage}")

        print("\n📈 RESULTS:")
        print(f"  Total Leads Generated: {results['total_leads_generated']}")
        print(f"  Total Leads Audited: {results['total_leads_audited']}")
        print(f"  Total Emails Generated: {results['total_emails_generated']}")

        if results["errors"]:
            print("\n⚠️  ERRORS:")
            for error in results["errors"][:5]:  # Show first 5 errors
                print(f"  • {error}")

        # Success metrics
        if results["total_leads_generated"] > 0:
            audit_rate = (
                results["total_leads_audited"] / results["total_leads_generated"]
            )
            email_rate = results["total_emails_generated"] / max(
                results["total_leads_audited"], 1
            )

            print("\n📊 SUCCESS METRICS:")
            print(f"  Audit Coverage: {audit_rate:.1%}")
            print(f"  Email Coverage: {email_rate:.1%}")

    def _record_pipeline_analytics(self, results: Dict):
        """Record pipeline execution analytics"""
        # Overall pipeline metrics
        self.repo.record_analytic(
            metric_name="pipeline_duration",
            metric_value=results["duration"],
            notes=f"Pipeline completed in {results['duration']:.1f}s",
        )

        self.repo.record_analytic(
            metric_name="pipeline_stages_completed",
            metric_value=len(results["stages_completed"]),
            notes=f"Stages: {', '.join(results['stages_completed'])}",
        )

        self.repo.record_analytic(
            metric_name="pipeline_stages_failed",
            metric_value=len(results["stages_failed"]),
            notes=f"Failed: {', '.join(results['stages_failed'])}"
            if results["stages_failed"]
            else "None",
        )

        # Stage-specific metrics
        if results["total_leads_generated"] > 0:
            self.repo.record_analytic(
                metric_name="leads_generated_per_run",
                metric_value=results["total_leads_generated"],
                notes="Total leads from Stage 0 + Stage A",
            )

        if results["total_leads_audited"] > 0:
            self.repo.record_analytic(
                metric_name="leads_audited_per_run",
                metric_value=results["total_leads_audited"],
                notes="Total leads audited in Stage B",
            )

        if results["total_emails_generated"] > 0:
            self.repo.record_analytic(
                metric_name="emails_generated_per_run",
                metric_value=results["total_emails_generated"],
                notes="Total emails generated in Stage C",
            )

    def schedule_pipeline_run(self, schedule_type: str = "daily") -> Dict:
        """Schedule pipeline runs (placeholder for future implementation)"""
        print(f"📅 Pipeline scheduling ({schedule_type}) - Feature coming soon!")
        return {
            "status": "scheduled",
            "schedule_type": schedule_type,
            "next_run": "TBD",
        }

    def get_pipeline_recommendations(self) -> List[str]:
        """Get pipeline optimization recommendations"""
        recommendations = []
        status = self.get_pipeline_status()

        # Check for bottlenecks
        db_stats = status["database_stats"]

        if db_stats.get("leads_by_status", {}).get("pending_audit", 0) > 100:
            recommendations.append(
                "🔧 Run Stage B auditor - large backlog of pending audits"
            )

        qualified_leads = db_stats.get("leads_by_status", {}).get("qualified", 0)
        total_emails = db_stats.get("emails_by_status", {}).get("total", 0)

        if qualified_leads > total_emails + 20:
            recommendations.append(
                "📧 Run Stage C email generator - qualified leads waiting for emails"
            )

        # Check pipeline health
        if status["pipeline_state"]["errors"]:
            recommendations.append(
                "🔍 Review pipeline errors - some stages are failing"
            )

        # Performance recommendations
        stage_stats = status.get("stage_stats", {})
        if stage_stats.get("stage_b", {}).get("qualification_rate", 0) < 0.3:
            recommendations.append("🎯 Review lead quality - low qualification rate")

        if stage_stats.get("stage_c", {}).get("personalization_avg", 0) < 0.6:
            recommendations.append(
                "✍️  Improve email personalization - low personalization scores"
            )

        if not recommendations:
            recommendations.append(
                "✅ Pipeline running smoothly - no immediate actions needed"
            )

        return recommendations
