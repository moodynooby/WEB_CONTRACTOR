from flask import Flask, jsonify, request, render_template
from flask_cors import CORS
import json
import threading
import subprocess
import sqlite3
import os

app = Flask(__name__)
CORS(app)

# Store process states
processes = {
    'scraper': False,
    'auditor': False,
    'email_generator': False,
    'email_sender': False,
    'analytics': False
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
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500
    
    try:
        cursor = conn.cursor()
        
        total_leads = cursor.execute('SELECT COUNT(*) FROM leads').fetchone()[0]
        qualified_leads = cursor.execute('SELECT COUNT(*) FROM audits WHERE qualified = 1').fetchone()[0]
        emails_sent = cursor.execute('SELECT COUNT(*) FROM email_campaigns WHERE status = "sent"').fetchone()[0]
        replies = cursor.execute('SELECT COUNT(*) FROM email_campaigns WHERE replied = 1').fetchone()[0]
        
        return jsonify({
            'totalLeads': total_leads,
            'qualifiedLeads': qualified_leads,
            'emailsSent': emails_sent,
            'replies': replies
        })
    except sqlite3.Error as e:
        return jsonify({'error': f'Database query failed: {e}'}), 500
    finally:
        conn.close()

@app.route('/api/leads', methods=['GET'])
def get_leads():
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500
    
    try:
        cursor = conn.cursor()
        leads = cursor.execute('''
            SELECT l.business_name, l.category, l.location, l.website, l.status 
            FROM leads l
        ''').fetchall()
        return jsonify([dict(ix) for ix in leads])
    except sqlite3.Error as e:
        return jsonify({'error': f'Database query failed: {e}'}), 500
    finally:
        conn.close()

@app.route('/api/process/start', methods=['POST'])
def start_process():
    process_key = request.json['process']
    
    # Map frontend names to filenames
    mapping = {
        'scraper': 'scraper.py',
        'auditor': 'auditor.py',
        'emailgen': 'email_generator.py',
        'sender': 'email_sender.py',
        'analytics': 'analytics.py'
    }
    
    script_name = mapping.get(process_key)
    if not script_name:
        return jsonify({'status': 'error', 'message': 'Unknown process'}), 400

    processes[process_key] = True

    # Start actual Python script
    subprocess.Popen(['python3', script_name])

    return jsonify({'status': 'started', 'process': process_key})

@app.route('/api/process/stop', methods=['POST'])
def stop_process():
    process_name = request.json['process']
    processes[process_name] = False
    # Note: This doesn't actually kill the process yet, just updates state.
    # For a full implementation, we'd track PIDs.
    return jsonify({'status': 'stopped'})

if __name__ == '__main__':
    app.run(debug=True, port=5000)
