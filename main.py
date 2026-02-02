from flask import Flask, jsonify, request, render_template, send_from_directory
from flask_cors import CORS
from flask_mail import Mail, Message
import json
import threading
import subprocess
import os
import time
from datetime import datetime, timedelta
from typing import Dict, List

# Import API utilities
from core.api_utils import (
    limiter, log_request, log_response, add_security_headers,
    handle_api_error, handle_validation_error, handle_general_error,
    validate_json, validate_query, rate_limit, success_response,
    ProcessStartSchema, ProcessStopSchema, LeadsQuerySchema, ReviewActionSchema,
    APIError, ValidationError
)
from loguru import logger

# Import new pipeline orchestrator
from core.pipeline_orchestrator import PipelineOrchestrator
# Import email utilities
from core.email_utils import send_email

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": ["http://localhost:3000", "http://127.0.0.1:3000"]}})

# Configure Flask-Mail
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.getenv('GMAIL_EMAIL')
app.config['MAIL_PASSWORD'] = os.getenv('GMAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.getenv('GMAIL_EMAIL')

# Initialize rate limiter
limiter.init_app(app)

# Register middleware
app.before_request(log_request)
app.after_request(log_response)
app.after_request(add_security_headers)

# Register error handlers
app.register_error_handler(APIError, handle_api_error)
app.register_error_handler(ValidationError, handle_validation_error)
app.register_error_handler(Exception, handle_general_error)

mail = Mail(app)

# Initialize pipeline orchestrator
pipeline = PipelineOrchestrator()
# Store process states and threads
processes = {
    'full_pipeline': {'running': False, 'thread': None, 'start_time': None, 'progress': 0},
    'stage0': {'running': False, 'thread': None, 'start_time': None, 'progress': 0},
    'stage_a': {'running': False, 'thread': None, 'start_time': None, 'progress': 0},
    'stage_b': {'running': False, 'thread': None, 'start_time': None, 'progress': 0},
    'stage_c': {'running': False, 'thread': None, 'start_time': None, 'progress': 0},
    'email_sender': {'running': False, 'thread': None, 'start_time': None, 'progress': 0}
}



@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/stats', methods=['GET'])
@rate_limit('30 per minute')
def get_stats():
    """Get comprehensive pipeline statistics"""
    try:
        pipeline_status = pipeline.get_pipeline_status()
        db_stats = pipeline_status['database_stats']
        
        # Extract key metrics for frontend
        total_leads = db_stats.get('total_leads', 0)
        qualified_leads = db_stats.get('leads_by_status', {}).get('qualified', 0)
        emails_sent = db_stats.get('emails_by_status', {}).get('sent', 0)
        replies = db_stats.get('emails_by_status', {}).get('replied', 0)
        
        # Get monthly progress from Stage 0
        monthly_progress = pipeline_status['stage_stats'].get('stage0', {})
        
        data = {
            'totalLeads': total_leads,
            'qualifiedLeads': qualified_leads,
            'emailsSent': emails_sent,
            'replies': replies,
            'monthlyProgress': monthly_progress,
            'pipelineState': pipeline_status['pipeline_state']
        }
        
        return success_response(data, 'Statistics retrieved successfully')
    except Exception as e:
        raise APIError(f'Stats retrieval failed: {e}', 500)

@app.route('/api/leads', methods=['GET'])
@rate_limit('60 per minute')
@validate_query(LeadsQuerySchema)
def get_leads():
    try:
        # Get validated query parameters
        page = request.validated_query['page']
        per_page = request.validated_query['per_page']
        status = request.validated_query['status']
        bucket = request.validated_query['bucket']
        
        from core.db import LeadRepository
        repo = LeadRepository()
        
        result = repo.get_leads(page, per_page, status, bucket)
        
        return success_response(result, f"Retrieved {len(result['leads'])} leads")
    except Exception as e:
        raise APIError(f'Database query failed: {e}', 500)

@app.route('/api/process/start', methods=['POST'])
@rate_limit('10 per minute')
@validate_json(ProcessStartSchema)
def start_process():
    """Start a pipeline process"""
    process_key = request.validated_json['process']
    
    if process_key not in processes:
        raise APIError('Invalid process', 400)
    
    if processes[process_key]['running']:
        raise APIError('Process already running', 400)
    
    def run_process():
        try:
            processes[process_key]['running'] = True
            processes[process_key]['start_time'] = datetime.now()
            processes[process_key]['progress'] = 0
            
            if process_key == 'full_pipeline':
                # Run complete pipeline
                results = pipeline.run_full_pipeline(manual_mode=True)
                processes[process_key]['progress'] = 100
                
            elif process_key == 'stage0':
                # Run Stage 0 only
                results = pipeline.run_individual_stage('stage0', daily_mode=True)
                processes[process_key]['progress'] = 100
                
            elif process_key == 'stage_a':
                # Run Stage A only
                results = pipeline.run_individual_stage('stage_a', max_queries_per_source=50)
                processes[process_key]['progress'] = 100
                
            elif process_key == 'stage_b':
                # Run Stage B only
                results = pipeline.run_individual_stage('stage_b', batch_size=50)
                processes[process_key]['progress'] = 100
                
            elif process_key == 'stage_c':
                # Run Stage C only
                results = pipeline.run_individual_stage('stage_c', batch_size=50)
                processes[process_key]['progress'] = 100
                
            elif process_key == 'email_sender':
                # Send pending emails
                # Re-implementing logic here to avoid circular dependencies and legacy code
                from core.db import LeadRepository
                repo = LeadRepository()
                
                pending_emails = repo.get_pending_emails_to_send(limit=50)
                sent_count = 0
                
                for email in pending_emails:
                    email_id = email['id']
                    lead_id = email['lead_id']
                    subject = email['subject']
                    body = email['body']
                    business_name = email['business_name']
                    
                    try:
                        # Fetch actual email from leads table
                        to_email = repo.get_lead_email(lead_id)
                        
                        if not to_email:
                            logger.error(f"Skipping {business_name} - No email found")
                            repo.update_campaign_status(email_id, 'failed', error_message="Verified email address not found; guessing is disabled.")
                            continue
                        
                        success = send_email(to_email, subject, body, mail)
                        
                        if success:
                            repo.update_campaign_status(email_id, 'sent', body)
                            sent_count += 1
                        else:
                            repo.update_campaign_status(email_id, 'failed', error_message="SMTP send failure")
                        
                        # Add delay between emails
                        time.sleep(30) # Fixed 30s delay between emails
                        
                    except Exception as e:
                        logger.error(f"Error processing pending email {email_id}: {e}")
                        repo.update_campaign_status(email_id, 'failed', error_message=str(e))
                
                logger.info(f"Process email_sender finished: {sent_count} sent")
                processes[process_key]['progress'] = 100
                
        except Exception as e:
            logger.error(f"Process {process_key} failed: {e}")
        finally:
            processes[process_key]['running'] = False
            processes[process_key]['thread'] = None
    
    thread = threading.Thread(target=run_process)
    thread.daemon = True
    thread.start()
    
    processes[process_key]['thread'] = thread
    
    return success_response({'process': process_key}, f'Started {process_key} process')

@app.route('/api/process/status', methods=['GET'])
@rate_limit('30 per minute')
def get_process_status():
    status = {}
    for key, process in processes.items():
        status[key] = {
            'running': process['running'],
            'progress': process['progress'],
            'start_time': process['start_time'].isoformat() if process['start_time'] else None
        }
    return success_response(status, 'Process status retrieved')

@app.route('/api/buckets', methods=['GET'])
@rate_limit('30 per minute')
def get_buckets():
    """Get all lead buckets with their configurations"""
    try:
        buckets = pipeline.stage0.bucket_manager.buckets
        bucket_list = []
        for bucket in buckets:
            bucket_list.append({
                'name': bucket.name,
                'categories': bucket.categories,
                'conversion_probability': bucket.conversion_probability,
                'monthly_target': bucket.monthly_target,
                'intent_profile': bucket.intent_profile
            })
        return success_response(bucket_list, f'Retrieved {len(bucket_list)} buckets')
    except Exception as e:
        raise APIError(f'Bucket retrieval failed: {e}', 500)

@app.route('/api/analytics', methods=['GET'])
@rate_limit('20 per minute')
def get_analytics():
    """Get detailed analytics data"""
    try:
        pipeline_status = pipeline.get_pipeline_status()
        
        from core.db import LeadRepository
        repo = LeadRepository()
        
        scraping_data = repo.get_scraping_logs(days=7)
        analytics_data = repo.get_recent_analytics(days=30)
        
        data = {
            'scraping_logs': scraping_data,
            'analytics': analytics_data,
            'pipeline_status': pipeline_status
        }
        
        return success_response(data, 'Analytics data retrieved successfully')
    except Exception as e:
        raise APIError(f'Analytics retrieval failed: {e}', 500)

@app.route('/api/process/stop', methods=['POST'])
@rate_limit('10 per minute')
@validate_json(ProcessStopSchema)
def stop_process():
    process_key = request.validated_json['process']
    
    if process_key not in processes:
        raise APIError('Invalid process', 400)
    
    if not processes[process_key]['running']:
        raise APIError('Process not running', 400)
    
    # Note: This is a simple implementation
    # In production, you'd want proper thread cleanup
    processes[process_key]['running'] = False
    processes[process_key]['progress'] = 0
    
    return success_response({'process': process_key}, f'Stopped {process_key} process')

# Add new API endpoints for pipeline management

@app.route('/api/pipeline/status', methods=['GET'])
@rate_limit('30 per minute')
def get_pipeline_status():
    """Get comprehensive pipeline status"""
    try:
        status = pipeline.get_pipeline_status()
        return success_response(status, 'Pipeline status retrieved')
    except Exception as e:
        raise APIError(f'Pipeline status retrieval failed: {e}', 500)

@app.route('/api/pipeline/recommendations', methods=['GET'])
@rate_limit('10 per minute')
def get_pipeline_recommendations():
    """Get pipeline optimization recommendations"""
    try:
        recommendations = pipeline.get_pipeline_recommendations()
        return success_response({'recommendations': recommendations}, 'Recommendations retrieved')
    except Exception as e:
        raise APIError(f'Recommendations retrieval failed: {e}', 500)


@app.route('/api/stages', methods=['GET'])
@rate_limit('30 per minute')
def get_stages():
    """Get available pipeline stages and their status"""
    stages = []
    for stage_key, config in pipeline.stage_configs.items():
        stage_info = {
            'key': stage_key,
            'name': stage_key.replace('_', ' ').title(),
            'enabled': config['enabled'],
            'schedule': config['schedule'],
            'priority': config['priority'],
            'running': processes.get(stage_key, {}).get('running', False)
        }
        stages.append(stage_info)
    
    return success_response({'stages': stages}, f'Retrieved {len(stages)} stages')
    
@app.route('/api/review/list', methods=['GET'])
@rate_limit('30 per minute')
def list_reviewable_emails():
    """List pending emails for leads that passed Stage B quality filter"""
    try:
        from core.db import LeadRepository
        repo = LeadRepository()
        
        emails = repo.get_reviewable_emails(0.7)
        # Parse analysis if needed (repo returns dicts which might have stringified json)
        for email in emails:
            if email.get('llm_analysis') and isinstance(email['llm_analysis'], str):
                try:
                    email['llm_analysis'] = json.loads(email['llm_analysis'])
                except:
                    pass
                    
        return success_response({'emails': emails}, f'Retrieved {len(emails)} reviewable emails')
    except Exception as e:
        raise APIError(f'Database query failed: {e}', 500)

@app.route('/api/review/action', methods=['POST'])
@rate_limit('10 per minute')
@validate_json(ReviewActionSchema)
def review_action():
    """Perform action on a pending email (send, ignore, edit)"""
    campaign_id = request.validated_json['campaignId']
    action = request.validated_json['action']
    body = request.validated_json.get('body')
    
    try:
        if action == 'ignore':
            repo.update_campaign_status(campaign_id, 'ignored')
            return success_response({'campaignId': campaign_id}, 'Email ignored')
            
        elif action == 'send':
            # Get email details first
            from core.db import LeadRepository
            repo = LeadRepository()
            
            row = repo.get_email_campaign(campaign_id)
            
            if not row:
                raise APIError('Campaign not found', 404)
                
            lead_email = row['email']
            if not lead_email:
                raise APIError(f"Cannot send: No email address for {row['business_name']}. Please edit the lead or run discovery to find an email.", 400)
            subject = row['subject']
            final_body = body if body else row['body']
            
            if send_email(lead_email, subject, final_body, mail):
                repo.update_campaign_status(campaign_id, 'sent', final_body)
                return success_response({'campaignId': campaign_id}, 'Email sent successfully')
            else:
                raise APIError('SMTP failure', 500)
        
        if action == 'approve':
            repo = LeadRepository() # Re-init locally just to be safe or reuse if desired
            repo.update_campaign_status(campaign_id, 'approved', body)
            return success_response({'campaignId': campaign_id}, 'Email approved for batch sending')
                
        raise APIError('Invalid action', 400)
    except APIError:
        raise
    except Exception as e:
        raise APIError(str(e), 500)

if __name__ == '__main__':
    app.run(debug=True, port=5000)
