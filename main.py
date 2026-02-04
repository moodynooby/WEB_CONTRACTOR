from flask import Flask, request, render_template
from flask_mail import Mail
import json
import threading
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

from core.api_utils import (
    handle_api_error,
    handle_general_error,
    success_response,
    APIError,
)
from core.db import LeadRepository
from core.pipeline_orchestrator import PipelineOrchestrator
from agents.stage_c_messaging import StageCEmailGenerator

app = Flask(__name__)

# Configure Flask-Mail
app.config["MAIL_SERVER"] = "smtp.gmail.com"
app.config["MAIL_PORT"] = 587
app.config["MAIL_USE_TLS"] = True
app.config["MAIL_USERNAME"] = os.getenv("GMAIL_EMAIL")
app.config["MAIL_PASSWORD"] = os.getenv("GMAIL_PASSWORD")
app.config["MAIL_DEFAULT_SENDER"] = os.getenv("GMAIL_EMAIL")

# Initialize components
mail = Mail(app)
repo = LeadRepository()
pipeline = PipelineOrchestrator()
hitl_sender = StageCEmailGenerator()

# Register error handlers
app.register_error_handler(APIError, handle_api_error)
app.register_error_handler(Exception, handle_general_error)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/stats", methods=["GET"])
def get_stats():
    """Get comprehensive pipeline statistics"""
    try:
        pipeline_status = pipeline.get_pipeline_status()
        db_stats = pipeline_status["database_stats"]

        # Extract key metrics for frontend
        total_leads = db_stats.get("total_leads", 0)
        qualified_leads = db_stats.get("leads_by_status", {}).get("qualified", 0)
        emails_sent = db_stats.get("emails_by_status", {}).get("sent", 0)
        replies = db_stats.get("emails_by_status", {}).get("replied", 0)

        # Get monthly progress from Stage 0
        monthly_progress = pipeline_status["stage_stats"].get("stage0", {})

        data = {
            "totalLeads": total_leads,
            "qualifiedLeads": qualified_leads,
            "emailsSent": emails_sent,
            "replies": replies,
            "monthlyProgress": monthly_progress,
            "pipelineState": pipeline_status["pipeline_state"],
        }

        return success_response(data, "Statistics retrieved successfully")
    except Exception as e:
        raise APIError(f"Stats retrieval failed: {e}", 500)


@app.route("/api/leads", methods=["GET"])
def get_leads():
    try:
        page = int(request.args.get("page", 1))
        per_page = min(int(request.args.get("per_page", 20)), 100)
        status = request.args.get("status", "")
        bucket = request.args.get("bucket", "")

        result = repo.get_leads(page, per_page, status, bucket)

        return success_response(result, f"Retrieved {len(result['leads'])} leads")
    except Exception as e:
        raise APIError(f"Database query failed: {e}", 500)


@app.route("/api/process/start", methods=["POST"])
def start_process():
    """Start a pipeline process"""
    process_key = request.json.get("process") if request.json else None

    # Special handling for email_sender which needs mail instance
    if process_key == "email_sender":

        def run_email_sender():
            try:
                pipeline.processes["email_sender"]["running"] = True
                pipeline.processes["email_sender"]["start_time"] = datetime.now()
                hitl_sender.set_mail_instance(mail)
                sent_count = hitl_sender.process_approved_emails(limit=50)
                print(f"Process email_sender finished: {sent_count} sent")
                pipeline.processes["email_sender"]["progress"] = 100
            except Exception as e:
                print(f"Email sender failed: {e}")
            finally:
                pipeline.processes["email_sender"]["running"] = False

        thread = threading.Thread(target=run_email_sender)
        thread.daemon = True
        thread.start()
        return success_response(
            {"process": process_key}, f"Started {process_key} process"
        )

    if pipeline.start_process(process_key):
        return success_response(
            {"process": process_key}, f"Started {process_key} process"
        )
    else:
        raise APIError("Failed to start process (invalid or already running)", 400)


@app.route("/api/process/status", methods=["GET"])
def get_process_status():
    status = pipeline.get_process_status()
    return success_response(status, "Process status retrieved")


@app.route("/api/buckets", methods=["GET"])
def get_buckets():
    """Get all lead buckets with their configurations"""
    try:
        buckets = pipeline.stage0.bucket_manager.buckets
        bucket_list = []
        for bucket in buckets:
            bucket_list.append(
                {
                    "name": bucket.name,
                    "categories": bucket.categories,
                    "conversion_probability": bucket.conversion_probability,
                    "monthly_target": bucket.monthly_target,
                    "intent_profile": bucket.intent_profile,
                }
            )
        return success_response(bucket_list, f"Retrieved {len(bucket_list)} buckets")
    except Exception as e:
        raise APIError(f"Bucket retrieval failed: {e}", 500)


@app.route("/api/analytics", methods=["GET"])
def get_analytics():
    """Get detailed analytics data"""
    try:
        pipeline_status = pipeline.get_pipeline_status()

        scraping_data = repo.get_scraping_logs(days=7)
        analytics_data = repo.get_recent_analytics(days=30)

        data = {
            "scraping_logs": scraping_data,
            "analytics": analytics_data,
            "pipeline_status": pipeline_status,
        }

        return success_response(data, "Analytics data retrieved successfully")
    except Exception as e:
        raise APIError(f"Analytics retrieval failed: {e}", 500)


@app.route("/api/process/stop", methods=["POST"])
def stop_process():
    process_key = request.json.get("process") if request.json else None

    if pipeline.stop_process(process_key):
        return success_response(
            {"process": process_key}, f"Stopped {process_key} process"
        )
    else:
        raise APIError("Process not running or invalid", 400)


@app.route("/api/pipeline/status", methods=["GET"])
def get_pipeline_status():
    """Get comprehensive pipeline status"""
    try:
        status = pipeline.get_pipeline_status()
        return success_response(status, "Pipeline status retrieved")
    except Exception as e:
        raise APIError(f"Pipeline status retrieval failed: {e}", 500)


@app.route("/api/pipeline/recommendations", methods=["GET"])
def get_pipeline_recommendations():
    """Get pipeline optimization recommendations"""
    try:
        recommendations = pipeline.get_pipeline_recommendations()
        return success_response(
            {"recommendations": recommendations}, "Recommendations retrieved"
        )
    except Exception as e:
        raise APIError(f"Recommendations retrieval failed: {e}", 500)


@app.route("/api/stages", methods=["GET"])
def get_stages():
    """Get available pipeline stages and their status"""
    stages = []
    for stage_key, config in pipeline.stage_configs.items():
        stage_info = {
            "key": stage_key,
            "name": stage_key.replace("_", " ").title(),
            "enabled": config["enabled"],
            "schedule": config["schedule"],
            "priority": config["priority"],
            "running": pipeline.processes.get(stage_key, {}).get("running", False),
        }
        stages.append(stage_info)

    return success_response({"stages": stages}, f"Retrieved {len(stages)} stages")


@app.route("/api/review/list", methods=["GET"])
def list_reviewable_emails():
    """List pending emails for leads that passed Stage B quality filter"""
    try:
        emails = repo.get_reviewable_emails(0.7)
        # Parse analysis if needed (repo returns dicts which might have stringified json)
        for email in emails:
            if email.get("llm_analysis") and isinstance(email["llm_analysis"], str):
                try:
                    email["llm_analysis"] = json.loads(email["llm_analysis"])
                except:
                    pass

        return success_response(
            {"emails": emails}, f"Retrieved {len(emails)} reviewable emails"
        )
    except Exception as e:
        raise APIError(f"Database query failed: {e}", 500)


@app.route("/api/review/action", methods=["POST"])
def review_action():
    """Perform action on a pending email (send, ignore, edit)"""
    data = request.json
    campaign_id = data["campaignId"]
    action = data["action"]
    body = data.get("body")

    try:
        if action == "ignore":
            repo.update_campaign_status(campaign_id, "ignored")
            return success_response({"campaignId": campaign_id}, "Email ignored")

        elif action == "send":
            hitl_sender.set_mail_instance(mail)
            if hitl_sender.send_single_email(campaign_id, body):
                return success_response(
                    {"campaignId": campaign_id}, "Email sent successfully"
                )
            else:
                raise APIError("Email sending failed", 500)

        elif action == "approve":
            repo.update_campaign_status(campaign_id, "approved", body)
            return success_response(
                {"campaignId": campaign_id}, "Email approved for batch sending"
            )

        raise APIError("Invalid action", 400)
    except APIError:
        raise
    except Exception as e:
        raise APIError(str(e), 500)


if __name__ == "__main__":
    app.run(debug=True, port=5000)
