from flask import Flask, jsonify, request, render_template, send_from_directory
from flask_cors import CORS
import json
import threading
import subprocess
import sqlite3
import os
import time
from datetime import datetime, timedelta
from typing import Dict, List

# Import new pipeline orchestrator
from core.pipeline_orchestrator import PipelineOrchestrator
from agents.quality_control_agent import QualityControlAgent

# Import legacy components for backward compatibility
from core.db import get_database_stats, log_scraping_session, record_analytic
from agents.email_sender import send_pending_emails

app = Flask(__name__)
CORS(app)

# Initialize pipeline orchestrator
pipeline = PipelineOrchestrator()
quality_control = QualityControlAgent()

# Store process states and threads
processes = {
    'full_pipeline': {'running': False, 'thread': None, 'start_time': None, 'progress': 0},
    'stage0': {'running': False, 'thread': None, 'start_time': None, 'progress': 0},
    'stage_a': {'running': False, 'thread': None, 'start_time': None, 'progress': 0},
    'stage_b': {'running': False, 'thread': None, 'start_time': None, 'progress': 0},
    'stage_c': {'running': False, 'thread': None, 'start_time': None, 'progress': 0},
    'quality_control': {'running': False, 'thread': None, 'start_time': None, 'progress': 0},
    'email_sender': {'running': False, 'thread': None, 'start_time': None, 'progress': 0}
}

def get_db_connection():
    try:
        conn = sqlite3.connect('leads.db')
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as e:
        print(f"Database connection error: {e}")
        return None

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Get comprehensive pipeline statistics"""
    try:
        pipeline_status = pipeline.get_pipeline_status()
        db_stats = pipeline_status['database_stats']
        quality_dashboard = pipeline_status['quality_dashboard']
        
        # Extract key metrics for frontend
        total_leads = db_stats.get('total_leads', 0)
        qualified_leads = quality_dashboard.get('qualified_leads', 0)
        emails_sent = db_stats.get('emails_by_status', {}).get('sent', 0)
        replies = db_stats.get('emails_by_status', {}).get('replied', 0)
        
        # Get monthly progress from Stage 0
        monthly_progress = pipeline_status['stage_stats'].get('stage0', {})
        
        return jsonify({
            'totalLeads': total_leads,
            'qualifiedLeads': qualified_leads,
            'emailsSent': emails_sent,
            'replies': replies,
            'monthlyProgress': monthly_progress,
            'pipelineState': pipeline_status['pipeline_state'],
            'qualityIssues': quality_dashboard.get('recent_alerts', 0)
        })
    except Exception as e:
        return jsonify({'error': f'Stats retrieval failed: {e}'}), 500

@app.route('/api/leads', methods=['GET'])
def get_leads():
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500
    
    try:
        cursor = conn.cursor()
        
        # Get query parameters
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 20))
        status = request.args.get('status', '')
        bucket = request.args.get('bucket', '')
        
        # Build query
        where_clause = "WHERE 1=1"
        params = []
        
        if status:
            where_clause += " AND l.status = ?"
            params.append(status)
        
        if bucket:
            where_clause += " AND l.bucket = ?"
            params.append(bucket)
        
        # Get total count
        count_query = f"SELECT COUNT(*) FROM leads l {where_clause}"
        total = cursor.execute(count_query, params).fetchone()[0]
        
        # Get paginated results
        offset = (page - 1) * per_page
        query = f'''
            SELECT l.business_name, l.category, l.location, l.website, l.status, l.quality_score, l.bucket, l.source
            FROM leads l
            {where_clause}
            ORDER BY l.created_at DESC
            LIMIT ? OFFSET ?
        '''
        leads = cursor.execute(query, params + [per_page, offset]).fetchall()
        
        return jsonify({
            'leads': [dict(ix) for ix in leads],
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': total,
                'pages': (total + per_page - 1) // per_page
            }
        })
    except sqlite3.Error as e:
        return jsonify({'error': f'Database query failed: {e}'}), 500
    finally:
        conn.close()

@app.route('/api/process/start', methods=['POST'])
def start_process():
    """Start a pipeline process"""
    process_key = request.json['process']
    
    if process_key not in processes:
        return jsonify({'error': 'Invalid process'}), 400
    
    if processes[process_key]['running']:
        return jsonify({'error': 'Process already running'}), 400
    
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
                
            elif process_key == 'quality_control':
                # Run quality control only
                results = pipeline.run_individual_stage('quality_control', comprehensive=True)
                processes[process_key]['progress'] = 100
                
            elif process_key == 'email_sender':
                # Send pending emails
                sent_count = send_pending_emails()
                processes[process_key]['progress'] = 100
                
        except Exception as e:
            print(f"Process {process_key} failed: {e}")
        finally:
            processes[process_key]['running'] = False
            processes[process_key]['thread'] = None
    
    thread = threading.Thread(target=run_process)
    thread.daemon = True
    thread.start()
    
    processes[process_key]['thread'] = thread
    
    return jsonify({'status': 'started'})

@app.route('/api/process/status', methods=['GET'])
def get_process_status():
    status = {}
    for key, process in processes.items():
        status[key] = {
            'running': process['running'],
            'progress': process['progress'],
            'start_time': process['start_time'].isoformat() if process['start_time'] else None
        }
    return jsonify(status)

@app.route('/api/buckets', methods=['GET'])
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
        return jsonify(bucket_list)
    except Exception as e:
        return jsonify({'error': f'Bucket retrieval failed: {e}'}), 500

@app.route('/api/analytics', methods=['GET'])
def get_analytics():
    """Get detailed analytics data"""
    try:
        pipeline_status = pipeline.get_pipeline_status()
        
        # Get scraping logs for last 7 days
        conn = get_db_connection()
        if not conn:
            return jsonify({'error': 'Database connection failed'}), 500
        
        cursor = conn.cursor()
        cursor.execute('''
            SELECT source, DATE(scrape_date) as date, 
                   SUM(leads_found) as found, 
                   SUM(leads_saved) as saved
            FROM scraping_logs 
            WHERE scrape_date >= date('now', '-7 days')
            GROUP BY source, DATE(scrape_date)
            ORDER BY date DESC
        ''')
        scraping_data = cursor.fetchall()
        
        # Get analytics metrics
        cursor.execute('''
            SELECT metric_name, metric_value, source, date_recorded
            FROM analytics 
            WHERE date_recorded >= date('now', '-30 days')
            ORDER BY date_recorded DESC
        ''')
        analytics_data = cursor.fetchall()
        
        conn.close()
        
        return jsonify({
            'scraping_logs': [dict(ix) for ix in scraping_data],
            'analytics': [dict(ix) for ix in analytics_data],
            'pipeline_status': pipeline_status,
            'quality_dashboard': pipeline_status['quality_dashboard']
        })
    except Exception as e:
        return jsonify({'error': f'Analytics retrieval failed: {e}'}), 500

@app.route('/api/process/stop', methods=['POST'])
def stop_process():
    process_key = request.json['process']
    
    if process_key not in processes:
        return jsonify({'error': 'Invalid process'}), 400
    
    if not processes[process_key]['running']:
        return jsonify({'error': 'Process not running'}), 400
    
    # Note: This is a simple implementation
    # In production, you'd want proper thread cleanup
    processes[process_key]['running'] = False
    processes[process_key]['progress'] = 0
    
    return jsonify({'status': 'stopped'})

# Add new API endpoints for pipeline management

@app.route('/api/pipeline/status', methods=['GET'])
def get_pipeline_status():
    """Get comprehensive pipeline status"""
    try:
        status = pipeline.get_pipeline_status()
        return jsonify(status)
    except Exception as e:
        return jsonify({'error': f'Pipeline status retrieval failed: {e}'}), 500

@app.route('/api/pipeline/recommendations', methods=['GET'])
def get_pipeline_recommendations():
    """Get pipeline optimization recommendations"""
    try:
        recommendations = pipeline.get_pipeline_recommendations()
        return jsonify({'recommendations': recommendations})
    except Exception as e:
        return jsonify({'error': f'Recommendations retrieval failed: {e}'}), 500

@app.route('/api/quality/check', methods=['POST'])
def run_quality_check():
    """Run quality control check"""
    if processes['quality_control']['running']:
        return jsonify({'error': 'Quality control already running'}), 400
    
    def run_qc():
        try:
            processes['quality_control']['running'] = True
            processes['quality_control']['start_time'] = datetime.now()
            processes['quality_control']['progress'] = 0
            
            results = quality_control.run_quality_check(comprehensive=True)
            processes['quality_control']['progress'] = 100
            
        except Exception as e:
            print(f"Quality control failed: {e}")
        finally:
            processes['quality_control']['running'] = False
            processes['quality_control']['thread'] = None
    
    thread = threading.Thread(target=run_qc)
    thread.daemon = True
    thread.start()
    
    processes['quality_control']['thread'] = thread
    
    return jsonify({'status': 'started'})

@app.route('/api/stages', methods=['GET'])
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
    
    return jsonify({'stages': stages})
    
@app.route('/api/review/list', methods=['GET'])
def list_reviewable_emails():
    """List pending emails for leads that passed Stage B quality filter"""
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500
    
    try:
        cursor = conn.cursor()
        # Filter for qualified leads with score >= 0.7
        query = '''
            SELECT 
                ec.id as campaign_id,
                l.id as lead_id,
                l.business_name,
                l.website,
                l.email as lead_email,
                a.overall_score,
                a.llm_analysis,
                ec.subject,
                ec.body,
                l.bucket
            FROM email_campaigns ec
            JOIN leads l ON ec.lead_id = l.id
            JOIN audits a ON l.id = a.lead_id
            WHERE ec.status = 'pending'
            AND a.overall_score >= 0.7
            AND a.qualified = 1
            ORDER BY a.overall_score DESC
        '''
        cursor.execute(query)
        emails = [dict(ix) for ix in cursor.fetchall()]
        
        # Parse JSON in llm_analysis if present
        for email in emails:
            if email['llm_analysis']:
                try:
                    email['llm_analysis'] = json.loads(email['llm_analysis'])
                except:
                    pass
                    
        return jsonify({'emails': emails})
    except sqlite3.Error as e:
        return jsonify({'error': f'Database query failed: {e}'}), 500
    finally:
        conn.close()

@app.route('/api/review/action', methods=['POST'])
def review_action():
    """Perform action on a pending email (send, ignore, edit)"""
    data = request.json
    campaign_id = data.get('campaignId')
    action = data.get('action') # 'send', 'ignore'
    body = data.get('body') # Optional revised body
    
    if not campaign_id or not action:
        return jsonify({'error': 'Missing campaignId or action'}), 400
        
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500
    
    try:
        cursor = conn.cursor()
        
        if action == 'ignore':
            cursor.execute('UPDATE email_campaigns SET status = "ignored" WHERE id = ?', (campaign_id,))
            conn.commit()
            return jsonify({'status': 'ignored'})
            
        elif action == 'send':
            # Get email details first
            cursor.execute('''
                SELECT l.email, l.business_name, l.id as lead_id, ec.subject, ec.body 
                FROM email_campaigns ec 
                JOIN leads l ON ec.lead_id = l.id 
                WHERE ec.id = ?
            ''', (campaign_id,))
            row = cursor.fetchone()
            
            if not row:
                return jsonify({'error': 'Campaign not found'}), 404
                
            lead_email = row['email'] or f"contact@{row['business_name'].lower().replace(' ', '')}.com"
            subject = row['subject']
            final_body = body if body else row['body']
            
            from agents.email_sender import send_email
            if send_email(lead_email, subject, final_body):
                cursor.execute('''
                    UPDATE email_campaigns 
                    SET status = "sent", body = ?, sent_at = ? 
                    WHERE id = ?
                ''', (final_body, datetime.now().isoformat(), campaign_id))
                conn.commit()
                return jsonify({'status': 'sent'})
            else:
                return jsonify({'error': 'SMTP failure'}), 500
                
        return jsonify({'error': 'Invalid action'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

if __name__ == '__main__':
    app.run(debug=True, port=5000)
